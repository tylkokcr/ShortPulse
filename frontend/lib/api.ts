import { supabase } from "./supabase";
import type {
  ArtStyle,
  CreditSummary,
  MusicTrack,
  CaptionTrack,
  Layout,
  Project,
  ProjectConfig,
  PublicPricing,
  RenderProgress,
  RenderTimings,
  SocialConnection,
  SocialPlatform,
  SocialPost,
  SubtitleStyle,
  TextOverlay,
  Voice,
  VisualModeAvailability,
} from "./types";

const API_BASE = "/api";

/**
 * Where the render-progress WebSocket connects.
 *
 * REST goes through the Next proxy at /api, but rewrites don't proxy
 * protocol upgrades, so the socket has to reach the backend itself.
 *
 * In development that is the same host on the backend's port. In a
 * deployment the backend is usually not on a port the browser can reach —
 * it sits behind the same reverse proxy as everything else — so
 * NEXT_PUBLIC_WS_ORIGIN overrides it with whatever address does work,
 * typically `wss://<your-domain>` with the proxy routing /ws to the API.
 */
function wsOrigin(): string {
  const configured = process.env.NEXT_PUBLIC_WS_ORIGIN;
  if (configured) return configured.replace(/\/$/, "");
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const port = process.env.NEXT_PUBLIC_BACKEND_PORT ?? "8000";
  return `${protocol}://${window.location.hostname}:${port}`;
}

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
    // A 422 here is a refusal with a sentence attached — an unavailable
    // visual mode, a topic the service will not generate. Showing the
    // sentence beats showing the JSON it arrived in.
    const reason = response.status === 422 ? serverReason(body) : null;
    throw new Error(reason ?? `${response.status} ${response.statusText}: ${body}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

/**
 * The sentence the server wrote for the user, out of a FastAPI error body.
 *
 * `detail` is a string on some routes and `{error, reason}` on others —
 * the second shape carries a code the UI can branch on alongside the
 * prose. Passing the object straight to `new Error` yields the literal
 * text "[object Object]", which is what the upload panel showed for
 * every 422 it had a good message for.
 *
 * Returns null when there is nothing worth showing, so the caller can
 * fall back to something that at least names the status.
 */
function serverReason(body: string): string | null {
  try {
    const detail = JSON.parse(body).detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail.reason === "string") return detail.reason;
  } catch {
    // Not JSON, or not shaped like an error we know.
  }
  return null;
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
  options: {
    language: string;
    title?: string;
    dubLanguage?: string;
    /** Turns the upload into an extraction: the transcript is read for
     *  the moments that stand up alone and each becomes its own project.
     *  Mutually exclusive with dubLanguage, which the API enforces. */
    clipCount?: number;
    subtitles?: SubtitleStyle;
    censorProfanity?: boolean;
    /** Free text telling the clip picker what to look for. Ignored
     *  unless clipCount is set. */
    clipGuidance?: string;
  },
  onProgress?: (fraction: number) => void
): Promise<Project> {
  const form = new FormData();
  form.append("file", file);
  form.append("language", options.language);
  form.append("title", options.title ?? "");
  // Empty means "no dub, just captions". `language` stays what the video
  // is spoken in either way — it is what the transcription pass is told.
  form.append("dub_language", options.dubLanguage ?? "");
  form.append("clip_count", String(options.clipCount ?? 0));
  form.append("censor_profanity", String(options.censorProfanity ?? false));
  form.append("clip_guidance", options.clipGuidance ?? "");
  // JSON inside a multipart field, because the file has to be multipart
  // and the style is a nested object. Omitted, the backend keeps its own
  // defaults — which is what this endpoint did for every upload until
  // now, picker on screen and all.
  if (options.subtitles) {
    form.append("subtitles", JSON.stringify(options.subtitles));
  }

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
        const reason = serverReason(xhr.responseText);
        if (reason) {
          reject(new Error(reason));
          return;
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

/**
 * Draw one scene again.
 *
 * Costs a credit, unlike an edit, and takes tens of seconds — one hosted
 * image generation plus a re-encode of the whole video. Both prompts are
 * optional: omitting them re-rolls the scene as it stands, which is the
 * common case when a picture simply came out wrong.
 *
 * A 402 arrives as InsufficientCreditsError through the shared request
 * helper, so callers get the balance and the price without parsing.
 */
export function regenerateScene(
  projectId: string,
  sceneIndex: number,
  body: { prompt?: string | null; negative_prompt?: string | null } = {}
): Promise<Project> {
  return request<Project>(`/projects/${projectId}/scenes/${sceneIndex}/regenerate`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * Say what came out wrong.
 *
 * Free, and the only signal of its kind — the privacy page rules out
 * third-party analytics, so this is how the product finds out whether its
 * output is any good. Returns the updated project, carrying the viewer's
 * own verdicts back so the UI can show a scene already flagged.
 */
export function submitFeedback(
  projectId: string,
  body: {
    scene_index?: number | null;
    rating: "up" | "down";
    reason?: string | null;
    note?: string | null;
  }
): Promise<Project> {
  return request<Project>(`/projects/${projectId}/feedback`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * Apply an edit and re-burn the video.
 *
 * Free and quick — it replays the burn-in pass over footage already on
 * disk rather than re-running the pipeline — so this resolves with the
 * updated project rather than handing back a job to watch.
 */
export function editProject(
  projectId: string,
  body: { captions?: CaptionTrack | null; overlays: TextOverlay[]; layout?: Layout }
): Promise<Project> {
  return request<Project>(`/projects/${projectId}/edit`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * Attach the bottom half of a split-screen layout.
 *
 * Separate from the edit call because the file is large and the edit is a
 * small document applied repeatedly — upload once, re-render as often as
 * you like.
 */
export async function uploadSecondaryClip(projectId: string, file: File): Promise<Project> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_BASE}/uploads/${projectId}/secondary`, {
    method: "POST",
    headers: await authHeaders(),
    body: form,
  });
  if (!response.ok) {
    const body = await response.text();
    try {
      throw new Error(JSON.parse(body).detail);
    } catch (err) {
      if (err instanceof Error && err.message) throw err;
      throw new Error(`Upload failed (${response.status})`);
    }
  }
  return response.json() as Promise<Project>;
}

/** Removes the row and everything it points at on disk. Irreversible. */
export function deleteProject(projectId: string): Promise<void> {
  return request<void>(`/projects/${projectId}`, { method: "DELETE" });
}

export function getCredits(): Promise<CreditSummary> {
  return request<CreditSummary>("/credits");
}

/**
 * The price list, without an account.
 *
 * The marketing page can't use getCredits(): a visitor isn't signed in,
 * and a deployment with REQUIRE_AUTH answers that 401 — which used to
 * leave the page quoting its hardcoded USD fallback while checkout
 * charged euros including VAT.
 */
export function getPublicPricing(): Promise<PublicPricing> {
  return request<PublicPricing>("/credits/packs");
}

export function listMusic(): Promise<MusicTrack[]> {
  return request<MusicTrack[]>("/music");
}

export function listArtStyles(): Promise<ArtStyle[]> {
  return request<ArtStyle[]>("/art-styles");
}

/**
 * Which visual modes this deployment can actually run.
 *
 * Asked rather than assumed because the pipeline hides its own failure:
 * a mode whose dependencies are missing still yields a video, silently
 * downgraded to stock footage. Offering it anyway means selling one thing
 * and delivering another.
 */
export function listVisualModes(): Promise<VisualModeAvailability[]> {
  return request<VisualModeAvailability[]>("/visual-modes");
}

export function listVoices(language: string): Promise<Voice[]> {
  return request<Voice[]>(`/voices?language=${encodeURIComponent(language)}`);
}

/**
 * Plain URLs rather than fetches: these feed <audio> elements, which
 * cannot carry an Authorization header.
 *
 * That used to come with "— and the preview endpoint needs none", which
 * was true on an install with no accounts and stopped being true the day
 * REQUIRE_AUTH was switched on. The endpoints are exempted in
 * api/middleware.py now, deliberately and for stated reasons, rather than
 * by assumption: a catalog sample belongs to nobody.
 */
export function voicePreviewUrl(voiceId: string): string {
  return `${API_BASE}/voices/preview?voice_id=${encodeURIComponent(voiceId)}`;
}

export function musicPreviewUrl(trackId: string): string {
  return `${API_BASE}/music/preview?track_id=${encodeURIComponent(trackId)}`;
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

/**
 * Begin a credit-pack purchase and return the URL to send the buyer to.
 *
 * Only the pack id is sent. Price and credit count are resolved server
 * side — a checkout that took an amount from the client would be a form
 * where the customer sets their own price.
 */
export function startCheckout(packId: string): Promise<{ url: string }> {
  return request<{ url: string }>("/credits/checkout", {
    method: "POST",
    body: JSON.stringify({ pack_id: packId }),
  });
}

/** Per-stage timings for a finished render. Resolves to an empty object
 *  when the project has none rather than throwing — a missing report is
 *  not an error worth surfacing. */
export function getRenderTimings(projectId: string): Promise<RenderTimings> {
  return request<RenderTimings>(`/projects/${projectId}/timings`);
}

/**
 * One frame of one scene, for the shot list.
 *
 * A plain URL because it feeds an <img>, and signed for the same reason
 * the video is: the element cannot send a header. Extracted from the
 * scene's own clip on first request and cached, so a breakdown costs one
 * seek per scene once and nothing afterwards.
 *
 * 404s for anything rendered before the working files were kept — the
 * caller shows the prompt alone, as it did before this existed.
 */
export function sceneThumbUrl(projectId: string, sceneIndex: number, token: string): string {
  return `${API_BASE}/projects/${projectId}/scenes/${sceneIndex}/thumb?token=${encodeURIComponent(token)}`;
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

    socket = new WebSocket(`${wsOrigin()}/ws/render/${projectId}${query}`);
    socket.onmessage = (event) => {
      onProgress(JSON.parse(event.data) as RenderProgress);
    };
  })();

  return () => {
    closed = true;
    socket?.close();
  };
}

// --------------------------------------------------------------------------
// Publishing
// --------------------------------------------------------------------------

export const getSocialPlatforms = () =>
  request<{ id: SocialPlatform; connected: boolean }[]>("/social/platforms");

export const getSocialConnections = () =>
  request<SocialConnection[]>("/social/connections");

/**
 * Start connecting an account.
 *
 * Returns a URL rather than navigating, because the caller decides when to
 * leave the page — and because the consent screen cannot be fetched, only
 * visited.
 */
export const startSocialConnect = (platform: SocialPlatform) =>
  request<{ url: string }>(`/social/connect/${platform}`, { method: "POST" });

export const setAutoPublish = (connectionId: string, auto_publish: boolean) =>
  request<void>(`/social/connections/${connectionId}`, {
    method: "PATCH",
    body: JSON.stringify({ auto_publish }),
  });

export const disconnectSocial = (connectionId: string) =>
  request<void>(`/social/connections/${connectionId}`, { method: "DELETE" });

export const getProjectPosts = (projectId: string) =>
  request<SocialPost[]>(`/social/posts/${projectId}`);

export const publishProject = (body: {
  project_id: string;
  connection_id: string;
  title: string;
  description: string;
  hashtags: string[];
}) =>
  request<SocialPost>("/social/posts", { method: "POST", body: JSON.stringify(body) });

/** Release a post the first-post rule held back. */
export const approvePost = (postId: string) =>
  request<SocialPost>(`/social/posts/${postId}/approve`, { method: "POST" });
