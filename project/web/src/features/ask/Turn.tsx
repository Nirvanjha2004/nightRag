import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  CircleSlash,
  Clock,
  HelpCircle,
  PencilLine,
  Sparkles,
  XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { VERDICT_LABEL } from "@/lib/stages";
import { formatDuration, sentence } from "@/lib/utils";
import { Answer } from "./Answer";
import { PipelineTrace } from "./PipelineTrace";
import { SourceDrawer } from "./SourceDrawer";
import { SourceList } from "./SourceList";
import type { Turn as TurnData } from "./useAsk";

const VERDICT_TONE = {
  correct: { tone: "positive", icon: CheckCircle2 },
  ambiguous: { tone: "caution", icon: HelpCircle },
  incorrect: { tone: "critical", icon: XCircle },
} as const;

export function Turn({ turn }: { turn: TurnData }) {
  const [openSource, setOpenSource] = useState<number | null>(null);
  const streaming = turn.status === "streaming";
  const verdict = turn.crag?.verdict;

  return (
    <article className="space-y-3 border-b border-line pb-8 last:border-b-0">
      <h2 className="text-[1.0625rem] font-semibold leading-snug tracking-tight text-fg">
        {turn.question}
      </h2>

      <div className="flex flex-wrap items-center gap-1.5">
        {verdict && (
          <Badge tone={VERDICT_TONE[verdict].tone} icon={VERDICT_TONE[verdict].icon}>
            {VERDICT_LABEL[verdict] ?? verdict}
          </Badge>
        )}
        {turn.crag && turn.crag.corrective_rounds > 0 && (
          <Badge tone="accent" icon={PencilLine}>
            {turn.crag.corrective_rounds} corrective round
            {turn.crag.corrective_rounds === 1 ? "" : "s"}
          </Badge>
        )}
        {turn.elapsedMs !== null && (
          <Badge tone="neutral" icon={Clock}>
            {formatDuration(turn.elapsedMs)}
          </Badge>
        )}
        {turn.status === "stopped" && (
          <Badge tone="caution" icon={CircleSlash}>
            Stopped
          </Badge>
        )}
      </div>

      {turn.crag?.rewritten_query && (
        <p className="rounded-control border border-accent-line bg-accent-soft px-3 py-2 text-xs leading-relaxed text-fg-muted">
          <span className="font-medium text-accent">Re-asked as: </span>
          <span className="font-mono">{turn.crag.rewritten_query}</span>
        </p>
      )}

      <PipelineTrace stages={turn.stages} live={streaming} />

      {turn.status === "error" ? (
        <div
          role="alert"
          className="flex items-start gap-2.5 rounded-card border border-critical/30 bg-critical-soft px-3.5 py-3"
        >
          <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0 text-critical" />
          <div className="min-w-0">
            <p className="text-[0.8125rem] font-medium text-fg">The question could not be answered</p>
            <p className="mt-1 break-words text-xs leading-relaxed text-fg-muted">{turn.error}</p>
          </div>
        </div>
      ) : turn.answer ? (
        <Answer text={turn.answer} streaming={streaming} />
      ) : streaming ? (
        <PendingAnswer />
      ) : null}

      <SourceList chunks={turn.chunks} onOpen={setOpenSource} />

      {turn.crag?.refinement && (
        <p className="text-xs text-fg-subtle">{sentence(turn.crag.refinement)}.</p>
      )}

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
      <p className="flex items-center gap-2 text-[0.8125rem] text-fg-muted">
        <Sparkles aria-hidden className="size-3.5 animate-pulse text-accent" />
        Writing the answer from the retrieved chunks…
      </p>
      <Skeleton className="h-3 w-[92%]" />
      <Skeleton className="h-3 w-[78%]" />
      <Skeleton className="h-3 w-[85%]" />
    </div>
  );
}
