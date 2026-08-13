import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  CircleSlash,
  HelpCircle,
  Sparkles,
  XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { formatDuration, sentence } from "@/lib/utils";
import { Answer } from "./Answer";
import { RetrievalLadder } from "./RetrievalLadder";
import { SourceDrawer } from "./SourceDrawer";
import { SourceList } from "./SourceList";
import type { Turn as TurnData } from "./useAsk";

const VERDICT = {
  correct: { tone: "keep", icon: CheckCircle2, label: "Retrieval correct" },
  ambiguous: { tone: "lamp", icon: HelpCircle, label: "Retrieval ambiguous" },
  incorrect: { tone: "cut", icon: XCircle, label: "Retrieval incorrect" },
} as const;

/**
 * One question and everything that happened because of it.
 *
 * Answer left, evidence right — the split is the argument: this tool claims
 * the answer came from those chunks and nothing else, so the two are never
 * more than a glance apart. On narrow screens the evidence falls below the
 * answer rather than into a tab, because a hidden citation is an unmade claim.
 */
export function Turn({ turn }: { turn: TurnData }) {
  const [openSource, setOpenSource] = useState<number | null>(null);
  const streaming = turn.status === "streaming";
  const verdict = turn.crag?.verdict;

  return (
    <article className="border-t border-rule pt-7 first:border-t-0 first:pt-0">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_17rem] lg:gap-8">
        <div className="min-w-0">
          <h2 className="display text-[1.375rem] font-semibold leading-[1.25] tracking-tight text-moon">
            {turn.question}
          </h2>

          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            {verdict && (
              <Badge tone={VERDICT[verdict].tone} icon={VERDICT[verdict].icon}>
                {VERDICT[verdict].label}
              </Badge>
            )}
            {turn.crag && turn.crag.corrective_rounds > 0 && (
              // Neutral, not lamp: the verdict beside it already carries the
              // amber, and two amber badges in a row spends the accent twice.
              <Badge tone="neutral">
                {turn.crag.corrective_rounds} corrective round
                {turn.crag.corrective_rounds === 1 ? "" : "s"}
              </Badge>
            )}
            {turn.elapsedMs !== null && (
              <span className="tally text-[0.6875rem] text-moon-3">
                {formatDuration(turn.elapsedMs)}
              </span>
            )}
            {turn.status === "stopped" && (
              <Badge tone="lamp" icon={CircleSlash}>
                Stopped
              </Badge>
            )}
          </div>

          {turn.crag?.rewritten_query && (
            <p className="mt-3 border-l-2 border-lamp-line pl-3 text-xs leading-relaxed text-moon-2">
              <span className="eyebrow mr-1.5">Re-asked</span>
              <span className="font-mono text-moon">{turn.crag.rewritten_query}</span>
            </p>
          )}

          <div className="mt-4">
            <RetrievalLadder stages={turn.stages} />
          </div>

          <div className="mt-5">
            {turn.status === "error" ? (
              <div
                role="alert"
                className="flex items-start gap-2.5 rounded-panel border border-cut/30 bg-cut-soft px-3.5 py-3"
              >
                <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0 text-cut" />
                <div className="min-w-0">
                  <p className="display text-[0.8125rem] font-semibold text-moon">
                    The question could not be answered
                  </p>
                  <p className="mt-1 break-words text-xs leading-relaxed text-moon-2">
                    {turn.error}
                  </p>
                </div>
              </div>
            ) : turn.answer ? (
              <Answer text={turn.answer} streaming={streaming} />
            ) : streaming ? (
              <PendingAnswer />
            ) : null}
          </div>

          {turn.crag?.refinement && (
            <p className="mt-3 text-xs text-moon-3">{sentence(turn.crag.refinement)}.</p>
          )}
        </div>

        {/* Sticky on wide screens: scrolling through a long answer should never
            scroll its evidence out of reach. */}
        <aside className="lg:sticky lg:top-6 lg:self-start">
          <SourceList chunks={turn.chunks} onOpen={setOpenSource} />
        </aside>
      </div>

      <SourceDrawer
        chunks={turn.chunks}
        index={openSource}
        onClose={() => setOpenSource(null)}
        onNavigate={setOpenSource}
      />
    </article>
  );
}

/** Shown between "retrieval finished" and "the first token arrived". */
function PendingAnswer() {
  return (
    <div className="space-y-2.5" role="status" aria-label="Generating the answer">
      <p className="flex items-center gap-2 text-[0.8125rem] text-moon-2">
        <Sparkles aria-hidden className="size-3.5 text-lamp breathing" />
        Writing from the kept chunks…
      </p>
      <Skeleton className="h-3 w-[92%]" />
      <Skeleton className="h-3 w-[78%]" />
      <Skeleton className="h-3 w-[85%]" />
    </div>
  );
}
