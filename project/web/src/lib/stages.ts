import {
  Combine,
  Database,
  Filter,
  GitMerge,
  ListOrdered,
  PencilLine,
  Scale,
  Search,
  SearchCheck,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import type { Verdict } from "./api";

/**
 * stages.ts — the pipeline stages the server can emit, in display order.
 *
 * `STAGE_ORDER` mirrors the constants in app/trace.py, plus the "index" stage
 * the server emits around building the retrievers. Unknown stages sort to the
 * end rather than the front, so a stage added server-side without a UI entry
 * never displaces the ones this UI knows about.
 */
export const STAGE_ORDER = [
  "index",
  "retrieve",
  "fuse",
  "rerank",
  "evaluate",
  "rewrite",
  "corrective_retrieve",
  "refine",
  "generate",
] as const;

interface StageMeta {
  label: string;
  hint: string;
  icon: LucideIcon;
}

const STAGE_META: Record<string, StageMeta> = {
  index: { label: "Indexes", hint: "Preparing retrieval indexes", icon: Database },
  retrieve: { label: "Retrieve", hint: "Hybrid BM25 + dense retrieval", icon: Search },
  fuse: { label: "Fuse", hint: "Merging both rank lists with RRF", icon: GitMerge },
  rerank: { label: "Rerank", hint: "LLM scores each candidate 1–5", icon: ListOrdered },
  evaluate: {
    label: "Evaluate",
    hint: "Retrieval graded correct, ambiguous or incorrect",
    icon: Scale,
  },
  rewrite: { label: "Rewrite", hint: "Question rewritten for another pass", icon: PencilLine },
  corrective_retrieve: {
    label: "Re-retrieve",
    hint: "Searching again with the rewritten question",
    icon: SearchCheck,
  },
  refine: { label: "Refine", hint: "Dropping chunks graded irrelevant", icon: Filter },
  generate: {
    label: "Generate",
    hint: "Writing the answer from the refined context",
    icon: Sparkles,
  },
};

const UNKNOWN_STAGE: StageMeta = { label: "Step", hint: "Running", icon: Combine };

export function stageMeta(stage: string): StageMeta {
  return STAGE_META[stage] ?? UNKNOWN_STAGE;
}

/** What the corrective grader decided, shown next to the answer. */
export const VERDICT_LABEL: Record<Verdict, string> = {
  correct: "Correct retrieval",
  ambiguous: "Ambiguous",
  incorrect: "Incorrect retrieval",
};
