import { memo } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

interface AnswerProps {
  text: string;
  streaming: boolean;
}

/**
 * The generated answer.
 *
 * Memoised on (text, streaming): a stream delivers dozens of deltas a second,
 * and re-parsing markdown is the expensive part of each one — everything else
 * in the turn must not re-render with it.
 */
export const Answer = memo(function Answer({ text, streaming }: AnswerProps) {
  return (
    <div
      // Polite, not assertive: an answer arriving must not interrupt whatever
      // the user is currently reading, but it should be announced when it
      // settles. `atomic=false` so only the new text is read, not the whole
      // answer again on every delta.
      aria-live="polite"
      aria-atomic="false"
      aria-busy={streaming}
      className={cn("prose-answer", streaming && "streaming-caret")}
    >
      <Markdown remarkPlugins={[remarkGfm]}>{text}</Markdown>
    </div>
  );
});
