import { useCallback, useEffect, useRef, useState } from "react";
import type { Chunk, CragTrace, PipelineOptions, StageEvent } from "@/lib/api";
import { askStream, type StreamEvent } from "@/lib/stream";

export type TurnStatus = "streaming" | "done" | "stopped" | "error";

export interface Turn {
  id: string;
  question: string;
  /** Stages in the order they first appeared, each holding its latest state. */
  stages: StageEvent[];
  chunks: Chunk[];
  crag: CragTrace | null;
  answer: string;
  status: TurnStatus;
  error: string | null;
  elapsedMs: number | null;
  prompt: string;
}

let nextTurnId = 1;

/**
 * Owns the conversation and the one in-flight request.
 *
 * Only a single question runs at a time — the pipeline is expensive and the
 * server holds one Qdrant client, so letting a user fan out five questions
 * would queue them anyway, just with a less honest UI. Asking again while a
 * stream is open aborts the old one first.
 */
export function useAsk(options: PipelineOptions) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Read the latest options at send time rather than baking them into the
  // callback: a settings change must apply to the next question without
  // re-creating (and thereby invalidating) every consumer of `ask`.
  const optionsRef = useRef(options);
  optionsRef.current = options;

  // Tokens are buffered and committed once per animation frame rather than on
  // every delta: a stream can deliver dozens of deltas a second, and each
  // commit re-parses the answer's markdown and re-renders the turn. Batching
  // caps that at one render per frame (~60/s), visually identical.
  const pendingTokensRef = useRef<{ id: string; text: string } | null>(null);
  const flushFrameRef = useRef<number | null>(null);

  const patch = useCallback((id: string, change: (turn: Turn) => Turn) => {
    setTurns((current) => current.map((turn) => (turn.id === id ? change(turn) : turn)));
  }, []);

  const flushTokens = useCallback(() => {
    flushFrameRef.current = null;
    const pending = pendingTokensRef.current;
    if (!pending) return;
    pendingTokensRef.current = null;
    patch(pending.id, (turn) => ({ ...turn, answer: turn.answer + pending.text }));
  }, [patch]);

  useEffect(
    () => () => {
      if (flushFrameRef.current !== null) cancelAnimationFrame(flushFrameRef.current);
      abortRef.current?.abort();
    },
    [],
  );

  const ask = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed) return;

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const id = `turn-${nextTurnId++}`;
      setTurns((current) => [
        ...current,
        {
          id,
          question: trimmed,
          stages: [],
          chunks: [],
          crag: null,
          answer: "",
          status: "streaming",
          error: null,
          elapsedMs: null,
          prompt: "",
        },
      ]);
      setBusy(true);

      const apply = (event: StreamEvent) => {
        switch (event.type) {
          case "stage":
            patch(id, (turn) => ({ ...turn, stages: upsertStage(turn.stages, event) }));
            break;
          case "context":
            patch(id, (turn) => ({
              ...turn,
              chunks: event.chunks,
              crag: event.crag,
              prompt: event.prompt,
            }));
            break;
          case "token": {
            // Append to the buffer and schedule one commit for the next frame.
            const pending = pendingTokensRef.current;
            if (pending && pending.id === id) {
              pending.text += event.text;
            } else {
              pendingTokensRef.current = { id, text: event.text };
            }
            if (flushFrameRef.current === null) {
              flushFrameRef.current = requestAnimationFrame(flushTokens);
            }
            break;
          }
          case "done":
            // Apply any buffered tokens before the terminal status lands.
            flushTokens();
            patch(id, (turn) => ({ ...turn, status: "done", elapsedMs: event.elapsed_ms }));
            break;
          case "error":
            flushTokens();
            patch(id, (turn) => ({ ...turn, status: "error", error: event.message }));
            break;
        }
      };

      try {
        await askStream({
          question: trimmed,
          options: optionsRef.current,
          signal: controller.signal,
          onEvent: apply,
        });
        // Apply whatever tokens were still buffered when the stream ended (the
        // user pressed Stop, or the connection dropped mid-answer) — keep the
        // text that arrived instead of discarding a partial answer.
        flushTokens();
        patch(id, (turn) =>
          turn.status === "streaming" ? { ...turn, status: "stopped" } : turn,
        );
      } catch (caught) {
        flushTokens();
        patch(id, (turn) => ({
          ...turn,
          status: "error",
          error: caught instanceof Error ? caught.message : "The request failed.",
        }));
      } finally {
        // Cancel any still-scheduled frame (the flush below commits it now).
        if (flushFrameRef.current !== null) cancelAnimationFrame(flushFrameRef.current);
        flushTokens();
        if (abortRef.current === controller) {
          abortRef.current = null;
          setBusy(false);
        }
      }
    },
    [patch],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
  }, []);

  const clear = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
    setTurns([]);
  }, []);

  return { turns, busy, ask, stop, clear };
}

/**
 * Replace a stage's entry in place, or append it the first time it is seen.
 *
 * Detail is merged rather than replaced: a stage reports different facts at
 * different moments (the hybrid retriever announces its dense/sparse split, the
 * orchestrator later announces how many chunks survived), and the UI wants all
 * of them on one row.
 */
function upsertStage(stages: StageEvent[], event: Extract<StreamEvent, { type: "stage" }>): StageEvent[] {
  const next: StageEvent = {
    stage: event.stage,
    status: event.status,
    message: event.message,
    detail: event.detail ?? {},
  };

  const index = stages.findIndex((stage) => stage.stage === event.stage);
  if (index === -1) return [...stages, next];

  const merged = [...stages];
  merged[index] = { ...next, detail: { ...stages[index].detail, ...next.detail } };
  return merged;
}
