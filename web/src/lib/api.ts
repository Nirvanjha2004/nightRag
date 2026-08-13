/**
 * api.ts — the HTTP client and the TypeScript mirror of server/schemas.py.
 *
 * The Pydantic models are the single source of truth; this file mirrors them
 * by hand, so keep field names in sync when either side changes.
 */

/**
 * Where the NightRag API lives, resolved in this order:
 *   1. window.__NIGHTRAG_API_URL__ — runtime override, set in your hosting
 *      provider's HTML/script so you can point at a backend without rebuilding.
 *   2. VITE_NIGHTRAG_API_URL — build-time env var. Set it on your frontend
 *      host (Vercel/Netlify/Render) before `npm run build`; Vite inlines
 *      VITE_-prefixed vars into the bundle.
 *   3. "" — same origin. The default: the FastAPI server serves the built UI
 *      and /api from the same port, so relative paths just work.
 *
 * Note: NIGHTRAG_API_URL (no VITE_ prefix) is NOT readable by client code —
 * it only configures the Vite dev proxy in vite.config.ts.
 */
export const API_BASE = (
  (window as { __NIGHTRAG_API_URL__?: string }).__NIGHTRAG_API_URL__ ??
  import.meta.env.VITE_NIGHTRAG_API_URL ??
  ""
).replace(/\/+$/, "");

export interface PipelineConfig {
  collection: string;
  model: string;
  top_k: number;
  rrf_k: number;
  candidate_k: number;
  min_score: number | null;
  rerank: boolean;
  crag: boolean;
}

/** Per-request overrides — anything absent falls back to the server default. */
export type PipelineOptions = Partial<PipelineConfig>;

export interface Collection {
  name: string;
  points: number;
  vector_size: number | null;
  indexed: boolean;
}

export interface Health {
  status: "ready" | "setup_required";
  version: string;
  storage: string;
  default_model: string;
  default_collection: string;
  missing_keys: string[];
  collections: Collection[];
  defaults: PipelineConfig;
}

export interface Chunk {
  text: string;
  file_path: string;
  node_type: string;
  name: string;
  start_line: number;
  end_line: number;
  score: number;
}

export type Verdict = "correct" | "ambiguous" | "incorrect";

/** What corrective RAG decided. All-null when CRAG is disabled. */
export interface CragTrace {
  verdict: Verdict | null;
  rewritten_query: string | null;
  corrective_rounds: number;
  refinement: string | null;
}

export type StageStatus = "start" | "done" | "skipped" | "error";

export interface StageEvent {
  stage: string;
  status: StageStatus;
  message: string | null;
  /** Stage-specific extras (counts, verdicts, timings) rendered generically. */
  detail: Record<string, unknown>;
}

export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export interface Job {
  id: string;
  status: JobStatus;
  source: string;
  target: string;
  collection: string;
  created_at: string;
  finished_at: string | null;
  logs: string[];
  error: string | null;
  summary: { chunks?: number; files?: number } | null;
}

export interface AskResponse {
  question: string;
  answer: string;
  chunks: Chunk[];
  crag: CragTrace;
  stages: StageEvent[];
  config: PipelineConfig;
  elapsed_ms: number;
  prompt: string;
}

/** A request reached the server but it said no — `message` is user-facing. */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status = 0) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    let message = `Request failed (HTTP ${response.status}).`;
    try {
      const body: unknown = await response.json();
      if (body && typeof body === "object" && "detail" in body) {
        const detail = (body as { detail: unknown }).detail;
        if (typeof detail === "string" && detail) message = detail;
      }
    } catch {
      /* non-JSON error body — keep the generic message */
    }
    throw new ApiError(message, response.status);
  }
  return (await response.json()) as T;
}

const JSON_HEADERS = { "Content-Type": "application/json" };

export const api = {
  /** Server status: keys, collections, defaults — one fetch for the whole UI. */
  health: () => request<Health>("/api/health"),

  /** Ingestion jobs, newest first. */
  jobs: () => request<Job[]>("/api/ingest/jobs"),

  /** Drop a collection and everything in it. */
  deleteCollection: (name: string) =>
    request<{ deleted: string }>(`/api/collections/${encodeURIComponent(name)}`, {
      method: "DELETE",
    }),

  /** Start an ingestion from a server-side path or a Git URL. */
  ingest: (source: "path" | "git", value: string, collection: string) =>
    request<Job>("/api/ingest", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ source, value, collection }),
    }),

  /** Start an ingestion from an uploaded .zip. */
  ingestUpload: (file: File, collection: string) => {
    const form = new FormData();
    form.append("file", file);
    if (collection) form.append("collection", collection);
    return request<Job>("/api/ingest/upload", { method: "POST", body: form });
  },
};
