import { supabase } from "./supabase";
import type { CreditSummary, Project, ProjectConfig, RenderProgress } from "./types";

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

export function getProject(projectId: string): Promise<Project> {
  return request<Project>(`/projects/${projectId}`);
}

export function listProjects(): Promise<Project[]> {
  return request<Project[]>("/projects");
}

export function getCredits(): Promise<CreditSummary> {
  return request<CreditSummary>("/credits");
}

export interface MediaUrl {
  /** Inline — what a <video> element needs. Served as an attachment, Chrome
   *  silently refuses to play it. */
  url: string;
  /** Attachment — saves with a sensible filename. */
  download_url: string;
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
 * Opens the render-progress WebSocket for a project. Returns a cleanup
 * function to close the socket; call it from a useEffect teardown.
 */
export function subscribeToRenderProgress(
  projectId: string,
  onProgress: (progress: RenderProgress) => void
): () => void {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  // The Next.js dev server proxy only rewrites /api/*, so the WebSocket
  // talks to the FastAPI backend directly. Same env var as next.config.mjs
  // (see frontend/.env.local.example) so both targets move together.
  const socket = new WebSocket(
    `${protocol}://${window.location.hostname}:${BACKEND_PORT}/ws/render/${projectId}`
  );

  socket.onmessage = (event) => {
    onProgress(JSON.parse(event.data) as RenderProgress);
  };

  return () => socket.close();
}
