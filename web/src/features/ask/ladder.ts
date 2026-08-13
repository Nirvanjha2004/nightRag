/**
 * ladder.ts — turn the raw stage trace into the funnel it actually describes.
 *
 * The pipeline reports stages, but the story underneath them is a cull: a wide
 * net of candidates narrowing to the handful the answer is written from. The
 * counts for that already exist, scattered across three stages' details —
 * `fuse` knows how many each retriever found and how many survived dedup,
 * `rerank` knows how many it kept, `refine` knows what corrective RAG dropped.
 *
 * This assembles them into one descending sequence, and interleaves the
 * decisions (a verdict, a rewrite) that have no count but change what happens
 * next. `retrieve` is deliberately not a row: it wraps the whole chain, so its
 * count is the same number `rerank` already reported, and showing it twice
 * would make the funnel look like it plateaued when it did not.
 */

import {
  CheckCircle2,
  Filter,
  Layers,
  ListOrdered,
  PencilLine,
  RefreshCw,
  Search,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import type { StageEvent, StageStatus } from "@/lib/api";

export interface LadderStep {
  key: string;
  label: string;
  /** Survivors after this step. Null for steps that decide rather than filter. */
  count: number | null;
  /** How many this step removed. Null when nothing was cut or it is not a filter. */
  cut: number | null;
  note: string | null;
  status: StageStatus;
  kind: "quantity" | "decision";
  icon: LucideIcon;
}

export interface Ladder {
  steps: LadderStep[];
  /** Widest bar, so every row is measured against the same scale. */
  max: number;
  /** True while any step is still running. */
  running: boolean;
}

function num(detail: Record<string, unknown>, key: string): number | null {
  const value = detail[key];
  return typeof value === "number" ? value : null;
}

export function buildLadder(stages: StageEvent[]): Ladder {
  const by = new Map(stages.map((stage) => [stage.stage, stage]));
  const steps: LadderStep[] = [];

  const push = (step: LadderStep) => steps.push(step);

  const index = by.get("index");
  if (index && index.status === "start") {
    push({
      key: "index",
      label: "Index",
      count: null,
      cut: null,
      note: index.message,
      status: index.status,
      kind: "decision",
      icon: Layers,
    });
  }

  const fuse = by.get("fuse");
  if (fuse) {
    const dense = num(fuse.detail, "dense");
    const sparse = num(fuse.detail, "sparse");
    const fused = num(fuse.detail, "fused");

    if (dense !== null && sparse !== null) {
      push({
        key: "searched",
        label: "Searched",
        count: dense + sparse,
        cut: null,
        note: `${dense} dense · ${sparse} BM25`,
        status: fuse.status,
        kind: "quantity",
        icon: Search,
      });
    }
    if (fused !== null) {
      const found = (dense ?? 0) + (sparse ?? 0);
      push({
        key: "fused",
        label: "Fused",
        count: fused,
        cut: found > fused ? found - fused : null,
        note: "reciprocal rank fusion, duplicates merged",
        status: fuse.status,
        kind: "quantity",
        icon: Layers,
      });
    }
  }

  const rerank = by.get("rerank");
  if (rerank) {
    const kept = num(rerank.detail, "count");
    const candidates = num(rerank.detail, "candidates");
    push({
      key: "reranked",
      label: "Reranked",
      count: kept,
      cut: kept !== null && candidates !== null && candidates > kept ? candidates - kept : null,
      note: rerank.message,
      status: rerank.status,
      kind: "quantity",
      icon: ListOrdered,
    });
  }

  const evaluate = by.get("evaluate");
  if (evaluate) {
    const verdict = evaluate.detail.verdict;
    push({
      key: "graded",
      label: "Graded",
      count: null,
      cut: null,
      note: typeof verdict === "string" ? verdict : evaluate.message,
      status: evaluate.status,
      kind: "decision",
      icon: CheckCircle2,
    });
  }

  const rewrite = by.get("rewrite");
  if (rewrite) {
    const query = rewrite.detail.query;
    push({
      key: "rewrote",
      label: "Rewrote",
      count: null,
      cut: null,
      note: typeof query === "string" ? query : rewrite.message,
      status: rewrite.status,
      kind: "decision",
      icon: PencilLine,
    });
  }

  const again = by.get("corrective_retrieve");
  if (again) {
    push({
      key: "re-retrieved",
      label: "Searched again",
      count: num(again.detail, "count"),
      cut: null,
      note: "second round on the rewritten query",
      status: again.status,
      kind: "quantity",
      icon: RefreshCw,
    });
  }

  // Whichever of these ran last decides the context the answer was written
  // from. Refine wins when corrective RAG is on; otherwise the orchestrator's
  // own retrieve count is the final word.
  const refine = by.get("refine");
  const retrieve = by.get("retrieve");
  const finalStage = refine ?? retrieve;
  if (finalStage) {
    push({
      key: "kept",
      label: "Kept",
      count: num(finalStage.detail, "count"),
      cut: null,
      note: refine ? refine.message : "handed to the model",
      status: finalStage.status,
      kind: "quantity",
      icon: Filter,
    });
  }

  const generate = by.get("generate");
  if (generate) {
    push({
      key: "answered",
      label: "Answered",
      count: null,
      cut: null,
      note: generate.status === "start" ? "writing from the kept chunks" : generate.message,
      status: generate.status,
      kind: "decision",
      icon: Sparkles,
    });
  }

  const counts = steps.map((step) => (step.count ?? 0) + (step.cut ?? 0));
  return {
    steps,
    max: Math.max(1, ...counts),
    running: steps.some((step) => step.status === "start"),
  };
}
