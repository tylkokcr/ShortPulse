import { supabase } from "./supabase";
import type {
  ArtStyle,
  CreditSummary,
  MusicTrack,
  Project,
  ProjectConfig,
  RenderProgress,
  Voice,
} from "./types";

const API_BASE = "/api";

// Must match next.config.mjs's rewrite target. REST goes through the Next
// proxy (/api/*), but the WebSocket connects to the backend directly, so
// it needs the port explicitly. Override in frontend/.env.local.
const BACKEND_PORT = process.env.NEXT_PUBLIC_BACKEND_PORT ?? "8000";

/**
 * The access token for the signed-in user, if there is one.
 *
 * getSession() refreshes an expired token rather than handing one back,
 * which matters because the backend refuses a token it can't verify
 * instead of falling back to anonymous — a stale token means 401, not a
 * free render.
 *
 * Returns no header on a self-hosted install, where requests are
 * anonymous by design.
 */
async function authHeaders(): Promise<Record<string, string>> {
  if (!supabase) return {};
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Thrown for 402, so the UI can offer a top-up instead of an error blob. */
export class InsufficientCreditsError extends Error {
  constructor(readonly balance: number, readonly required: number) {
    super(`Not enough credits: ${balance} available, ${required} needed`);
    this.name = "InsufficientCreditsError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(await authHeaders()),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const body = await response.text();
    if (response.status === 402) {
      try {
        const detail = JSON.parse(body).detail;
        throw new InsufficientCreditsError(detail.balance, detail.required);
      } catch (err) {
        if (err instanceof InsufficientCreditsError) throw err;
      }
    }
    throw new Error(`${response.status} ${response.statusText}: ${body}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function createProject(config: Partial<ProjectConfig> & { topic: string }): Promise<Project> {
  return request<Project>("/projects", {
    method: "POST",
    body: JSON.stringify(config),
  });
}

/**
 * Upload a video to be captioned.
 *
 * Uses XHR rather than fetch for one reason: upload progress. `fetch` has
 * no equivalent of `upload.onprogress`, and a 200MB file over a phone
 * connection with no progress bar looks like a hung page.
 *
 * The response is an ordinary Project, already queued — from here on the
 * caller watches it over the same render-progress socket as a generated
 * one.
 */
export async function uploadVideo(
  file: File,
  options: { language: string; title?: string },
  onProgress?: (fraction: number) => void
): Promise<Project> {
  const form = new FormData();
  form.append("file", file);
  form.append("language", options.language);
  form.append("title", options.title ?? "");

  const headers = await authHeaders();

  return new Promise<Project>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/uploads`);
    for (const [key, value] of Object.entries(headers)) {
      xhr.setRequestHeader(key, value);
    }
    // Deliberately no Content-Type: the browser has to set it, because
    // only it knows the multipart boundary it generated.

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(event.loaded / event.total);
    };

    xhr.onload = () => {
      if (xhr.status === 201) {
        resolve(JSON.parse(xhr.responseText) as Project);
        return;
      }
      if (xhr.status === 402) {
        try {
          const detail = JSON.parse(xhr.responseText).detail;
          reject(new InsufficientCreditsError(detail.balance, detail.required));
          return;
        } catch {
          // fall through to the generic error below
        }
      }
      if (xhr.status === 422) {
        // The server's reason is written for the user ("no audio track",
        // "larger than the 200MB limit") — showing it beats a status code.
        try {
          reject(new Error(JSON.parse(xhr.responseText).detail));
          return;
        } catch {
          // fall through
        }
      }
      reject(new Error(`Upload failed (${xhr.status}): ${xhr.responseText.slice(0, 200)}`));
    };

    xhr.onerror = () => reject(new Error("Upload failed — check your connection."));
    xhr.onabort = () => reject(new Error("Upload cancelled."));

    xhr.send(form);
  });
}

export function getProject(projectId: string): Promise<Project> {
  return request<Project>(`/projects/${projectId}`);
}

export function listProjects(): Promise<Project[]> {
  return request<Project[]>("/projects");
}

/** Removes the row and everything it points at on disk. Irreversible. */
export function deleteProject(projectId: string): Promise<void> {
  return request<void>(`/projects/${projectId}`, { method: "DELETE" });
}

export function getCredits(): Promise<CreditSummary> {
  return request<CreditSummary>("/credits");
}

export function listMusic(): Promise<MusicTrack[]> {
  return request<MusicTrack[]>("/music");
}

export function listArtStyles(): Promise<ArtStyle[]> {
  return request<ArtStyle[]>("/art-styles");
}

export function listVoices(language: string): Promise<Voice[]> {
  return request<Voice[]>(`/voices?language=${encodeURIComponent(language)}`);
}

/** Plain URL rather than a fetch: it feeds an <audio> element, which can't
 *  carry an Authorization header — and the preview endpoint needs none. */
export function voicePreviewUrl(voiceId: string): string {
  return `${API_BASE}/voices/preview?voice_id=${encodeURIComponent(voiceId)}`;
}

export interface MediaUrl {
  /** Inline — what a <video> element needs. Served as an attachment, Chrome
   *  silently refuses to play it. */
  url: string;
  /** Attachment — saves with a sensible filename. */
  download_url: string;
  /** Still frame extracted after the render. 404s for projects rendered
   *  before posters existed — callers should tolerate it failing. */
  poster_url: string;
  expires_at: number;
}

/**
 * A short-lived URL for the rendered video.
 *
 * A <video> tag can't send an Authorization header, so ownership is
 * checked here — on a request that can — and the returned URL carries a
 * signed token instead. Fetch a fresh one rather than holding onto it:
 * they expire in minutes.
 */
export function getMediaUrl(projectId: string): Promise<MediaUrl> {
  return request<MediaUrl>(`/projects/${projectId}/media-url`);
}

/** A credential for the progress WebSocket, which can't carry a header
 *  either. Available while the render is still running, unlike a media URL. */
export function getStreamToken(projectId: string): Promise<{ token: string; expires_at: number }> {
  return request(`/projects/${projectId}/stream-token`);
}

/**
 * Opens the render-progress WebSocket for a project. Returns a cleanup
 * function to close the socket; call it from a useEffect teardown.
 */
export function subscribeToRenderProgress(
  projectId: string,
  onProgress: (progress: RenderProgress) => void
): () => void {
  let socket: WebSocket | null = null;
  let closed = false;

  // The token has to be fetched first, so the socket opens a moment after
  // this returns. The cleanup flag covers a component that unmounts in
  // between — without it the socket would open with nobody listening and
  // never be closed.
  (async () => {
    let query = "";
    try {
      const { token } = await getStreamToken(projectId);
      query = `?token=${encodeURIComponent(token)}`;
    } catch {
      // Self-hosted installs have no accounts and the socket needs no
      // token there; anything else will be refused by the server.
    }
    if (closed) return;

    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    // The Next.js dev server proxy only rewrites /api/*, so the WebSocket
    // talks to the FastAPI backend directly. Same env var as next.config.mjs
    // (see frontend/.env.local.example) so both targets move together.
    socket = new WebSocket(
      `${protocol}://${window.location.hostname}:${BACKEND_PORT}/ws/render/${projectId}${query}`
    );
    socket.onmessage = (event) => {
      onProgress(JSON.parse(event.data) as RenderProgress);
    };
  })();

  return () => {
    closed = true;
    socket?.close();
  };
}
