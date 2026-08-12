import { ApiError, type Chunk, type CragTrace, type PipelineOptions, type StageStatus } from "./api";

/**
 * stream.ts — the SSE consumer for /api/ask/stream.
 *
 * The server streams Server-Sent Events over POST (the EventSource API is
 * GET-only), so this reads a fetch ReadableStream instead. Each event is one
 * `data: {json}` line followed by a blank line; see server/routes.py for the
 * shapes, which this union mirrors.
 */
export type StreamEvent =
  | {
      type: "stage";
      stage: string;
      status: StageStatus;
      message: string | null;
      detail?: Record<string, unknown>;
    }
  | { type: "context"; chunks: Chunk[]; crag: CragTrace; prompt: string }
  | { type: "token"; text: string }
  | { type: "done"; elapsed_ms: number }
  | { type: "error"; message: string };

interface AskStreamParams {
  question: string;
  options: PipelineOptions;
  /**
   * Aborting makes the stream stop cleanly: askStream resolves (it does not
   * throw), so the caller can mark the turn "stopped" instead of "error".
   */
  signal?: AbortSignal;
  onEvent: (event: StreamEvent) => void;
}

export async function askStream({ question, options, signal, onEvent }: AskStreamParams): Promise<void> {
  let response: Response;
  try {
    response = await fetch("/api/ask/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, options }),
      signal,
    });
  } catch (caught) {
    // The request was cancelled before it left — the user pressed Stop.
    if (signal?.aborted) return;
    throw caught;
  }

  if (!response.ok) {
    let message = `The question could not be asked (HTTP ${response.status}).`;
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

  const reader = response.body?.getReader();
  if (!reader) throw new Error("The server did not return a readable stream.");

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Events are separated by a blank line. A partial event at the end of
      // the chunk stays in the buffer until the rest of it arrives.
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() ?? "";
      for (const block of blocks) {
        const event = parseEvent(block);
        if (event) onEvent(event);
      }
    }
  } catch (caught) {
    // Stop pressed mid-stream — the bytes read so far are kept by the caller.
    if (signal?.aborted) return;
    throw caught;
  }
}

/** One `data: {...}` block → a typed event, or null for anything else. */
function parseEvent(block: string): StreamEvent | null {
  const trimmed = block.trim();
  if (!trimmed.startsWith("data:")) return null;
  const payload = trimmed.slice(5).trim();
  if (!payload) return null;

  try {
    const event = JSON.parse(payload) as StreamEvent;
    if (!event || typeof event !== "object" || !("type" in event)) return null;
    return event;
  } catch {
    return null;
  }
}
