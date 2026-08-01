import type { Project, ProjectConfig, RenderProgress } from "./types";

const API_BASE = "/api";

// Must match next.config.mjs's rewrite target. REST goes through the Next
// proxy (/api/*), but the WebSocket connects to the backend directly, so
// it needs the port explicitly. Override in frontend/.env.local.
const BACKEND_PORT = process.env.NEXT_PUBLIC_BACKEND_PORT ?? "8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const body = await response.text();
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

export function downloadUrl(projectId: string): string {
  return `${API_BASE}/projects/${projectId}/download`;
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
