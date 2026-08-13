import { motion } from "framer-motion";
import { AlertTriangle, Loader2, MinusCircle } from "lucide-react";
import type { StageEvent } from "@/lib/api";
import { buildLadder, type LadderStep } from "./ladder";
import { cn, sentence } from "@/lib/utils";

/**
 * The cull ladder — this interface's one bold element.
 *
 * Retrieval is elimination: sixteen candidates found, twelve after dedup, five
 * after the reranker, and those five write the answer. A checklist of stage
 * names hides that; a descending set of bars is the shape of the thing itself,
 * and the width of each bar is a real measurement rather than a decoration.
 *
 * Only two rows are allowed colour. The row still running is lit by the lamp —
 * that glow is the progress indicator, which is the only reason it may glow at
 * all — and the final row is mint, because "what survived" is the one quantity
 * the reader is actually being asked to trust. Everything between them is
 * steel, so the rose discards are the thing the eye catches.
 *
 * It sits above the answer deliberately: the answer's credibility rests on
 * these numbers, so they are read first, and they are compressed hard so that
 * reading them costs a glance rather than a scroll.
 */
export function RetrievalLadder({ stages }: { stages: StageEvent[] }) {
  const ladder = buildLadder(stages);
  if (ladder.steps.length === 0) return null;

  return (
    <section
      aria-label="Retrieval funnel"
      className="rounded-panel border border-rule bg-panel px-3.5 py-3 shadow-[var(--shadow-panel)]"
    >
      <header className="mb-2 flex items-baseline justify-between gap-3">
        <h3 className="eyebrow">Retrieval</h3>
        <p className="text-[0.6875rem] text-moon-3">
          {ladder.running ? "running" : "candidates narrowed to the answer's context"}
        </p>
      </header>

      <ol>
        {ladder.steps.map((step) => (
          <Row key={step.key} step={step} max={ladder.max} />
        ))}
      </ol>
    </section>
  );
}

function Row({ step, max }: { step: LadderStep; max: number }) {
  const live = step.status === "start";
  const failed = step.status === "error";
  const skipped = step.status === "skipped";
  const final = step.key === "kept";

  const kept = step.count ?? 0;
  const cut = step.cut ?? 0;

  // A decision changes what happens next but measures nothing, so it gets one
  // tight line and no bar — which is also what keeps the whole panel short.
  if (step.kind === "decision") {
    return (
      <li
        className={cn(
          "grid grid-cols-[2.25rem_1fr] items-baseline gap-3 rounded-control px-1.5 py-1",
          live && "bg-lamp-soft",
        )}
      >
        <span className="flex justify-end">
          {live ? (
            <Loader2 aria-hidden className="size-3 animate-spin text-lamp" />
          ) : failed ? (
            <AlertTriangle aria-hidden className="size-3 text-cut" />
          ) : skipped ? (
            <MinusCircle aria-hidden className="size-3 text-moon-3" />
          ) : (
            <span aria-hidden className="h-px w-2.5 bg-rule-strong" />
          )}
        </span>
        <span className="flex min-w-0 items-baseline gap-2">
          <span
            className={cn(
              "display text-[0.75rem] font-semibold",
              live ? "text-lamp" : failed ? "text-cut" : "text-moon-2",
            )}
          >
            {step.label}
          </span>
          {step.note && (
            <span className="min-w-0 flex-1 truncate text-right text-[0.6875rem] text-moon-3">
              {sentence(step.note)}
            </span>
          )}
        </span>
      </li>
    );
  }

  return (
    <li
      className={cn(
        "grid grid-cols-[2.25rem_1fr] items-center gap-3 rounded-control px-1.5 py-1",
        live && "lit bg-lamp-soft",
      )}
    >
      <span
        className={cn(
          "tally text-right text-[1.0625rem] leading-none",
          live ? "text-lamp" : final ? "text-keep" : "text-moon",
        )}
      >
        {step.count ?? "·"}
      </span>

      <div className="min-w-0">
        <div className="flex items-baseline gap-2">
          <span
            className={cn(
              "display text-[0.75rem] font-semibold",
              live ? "text-lamp" : failed ? "text-cut" : "text-moon",
            )}
          >
            {step.label}
          </span>
          {cut > 0 && <span className="text-[0.6875rem] text-cut">−{cut}</span>}
          {step.note && (
            <span className="min-w-0 flex-1 truncate text-right text-[0.6875rem] text-moon-3">
              {sentence(step.note)}
            </span>
          )}
        </div>

        <div className="mt-1 flex h-1 w-full overflow-hidden rounded-pill bg-panel-2">
          {/* Survivors, then the ghost of what this step removed — together they
              always span what the step was handed. */}
          <motion.span
            layout
            initial={{ width: 0 }}
            animate={{ width: `${(kept / max) * 100}%` }}
            transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
            className={cn(
              "h-full rounded-pill",
              live
                ? "bg-lamp breathing"
                : failed
                  ? "bg-cut"
                  : final
                    ? "bg-keep"
                    : "bg-moon-3",
            )}
          />
          {cut > 0 && (
            <motion.span
              layout
              initial={{ width: 0 }}
              animate={{ width: `${(cut / max) * 100}%` }}
              transition={{ duration: 0.45, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}
              className="h-full bg-cut/35"
            />
          )}
        </div>
      </div>
    </li>
  );
}
