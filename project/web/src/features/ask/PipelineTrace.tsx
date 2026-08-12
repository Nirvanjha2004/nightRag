import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Check, ChevronRight, Loader2, MinusCircle } from "lucide-react";
import type { StageEvent, StageStatus } from "@/lib/api";
import { STAGE_ORDER, stageMeta } from "@/lib/stages";
import { cn, sentence } from "@/lib/utils";

const STATUS_STYLE: Record<StageStatus, { dot: string; text: string }> = {
  start: { dot: "border-accent text-accent", text: "text-fg" },
  done: { dot: "border-positive/50 text-positive", text: "text-fg" },
  skipped: { dot: "border-line-strong text-fg-subtle", text: "text-fg-muted" },
  error: { dot: "border-critical/50 text-critical", text: "text-fg" },
};

const STATUS_LABEL: Record<StageStatus, string> = {
  start: "running",
  done: "done",
  skipped: "skipped",
  error: "failed",
};

interface PipelineTraceProps {
  stages: StageEvent[];
  /** True while the pipeline is still running this turn. */
  live?: boolean;
}

export function PipelineTrace({ stages, live = false }: PipelineTraceProps) {
  const [open, setOpen] = useState(live);

  // Open while the pipeline runs (that is when watching it is worth the space),
  // then fold away on completion — an old turn's trace is evidence you go
  // looking for, not something to scroll past on the way to the next answer.
  // A user who opened or closed it themselves keeps their choice.
  const touched = useRef(false);
  useEffect(() => {
    if (!touched.current) setOpen(live);
  }, [live]);

  if (stages.length === 0) return null;

  const ordered = [...stages].sort(
    (a, b) => orderOf(a.stage) - orderOf(b.stage),
  );
  const running = ordered.find((stage) => stage.status === "start");
  const failed = ordered.filter((stage) => stage.status === "error").length;

  return (
    <div className="overflow-hidden rounded-card border border-line bg-surface">
      <button
        type="button"
        onClick={() => {
          touched.current = true;
          setOpen((value) => !value);
        }}
        aria-expanded={open}
        className={cn(
          "flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left transition-colors",
          "hover:bg-surface-hover",
        )}
      >
        <ChevronRight
          aria-hidden
          className={cn(
            "size-3.5 shrink-0 text-fg-subtle transition-transform duration-200",
            open && "rotate-90",
          )}
        />
        <span className="text-[0.8125rem] font-medium text-fg">Pipeline</span>

        {/* Collapsed summary: a dot per stage, so progress is legible without
            expanding — plus a text status for anyone who cannot use the dots. */}
        <span aria-hidden className="flex items-center gap-1">
          {ordered.map((stage) => (
            <span
              key={stage.stage}
              className={cn(
                "size-1.5 rounded-pill",
                stage.status === "done" && "bg-positive",
                stage.status === "start" && "animate-pulse bg-accent",
                stage.status === "skipped" && "bg-line-strong",
                stage.status === "error" && "bg-critical",
              )}
            />
          ))}
        </span>

        <span className="ml-auto truncate text-xs text-fg-muted">
          {running
            ? stageMeta(running.stage).label + "…"
            : failed > 0
              ? `${ordered.length} steps, ${failed} degraded`
              : `${ordered.length} steps`}
        </span>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="overflow-hidden"
          >
            <ol className="space-y-0 border-t border-line px-3.5 py-1">
              {ordered.map((stage, index) => (
                <StageRow key={stage.stage} stage={stage} last={index === ordered.length - 1} />
              ))}
            </ol>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function StageRow({ stage, last }: { stage: StageEvent; last: boolean }) {
  const meta = stageMeta(stage.stage);
  const style = STATUS_STYLE[stage.status];
  const Icon = meta.icon;

  return (
    <li className="relative flex gap-3 py-2.5">
      {/* The rail connecting one step to the next. */}
      {!last && <span aria-hidden className="absolute left-[0.6875rem] top-8 bottom-0 w-px bg-line" />}

      <span
        className={cn(
          "relative z-10 mt-0.5 flex size-[1.375rem] shrink-0 items-center justify-center rounded-pill border bg-surface",
          style.dot,
        )}
      >
        {stage.status === "start" ? (
          <Loader2 aria-hidden className="size-3 animate-spin" />
        ) : stage.status === "done" ? (
          <Check aria-hidden className="size-3" strokeWidth={3} />
        ) : stage.status === "error" ? (
          <AlertTriangle aria-hidden className="size-3" />
        ) : (
          <MinusCircle aria-hidden className="size-3" />
        )}
      </span>

      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className={cn("text-[0.8125rem] font-medium", style.text)}>{meta.label}</span>
          <span className="text-[0.6875rem] text-fg-subtle">{STATUS_LABEL[stage.status]}</span>
          <Icon aria-hidden className="ml-auto size-3.5 shrink-0 text-fg-subtle" />
        </div>
        <p className="mt-0.5 text-xs leading-relaxed text-fg-muted">
          {sentence(stage.message ?? meta.hint)}
        </p>
      </div>
    </li>
  );
}

function orderOf(stage: string): number {
  const index = STAGE_ORDER.indexOf(stage as (typeof STAGE_ORDER)[number]);
  // Unknown stages sort to the end rather than to the front, so a stage added
  // in Python without a UI entry never displaces the ones that are known.
  return index === -1 ? STAGE_ORDER.length : index;
}
