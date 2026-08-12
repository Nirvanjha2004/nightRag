import type { Chunk } from "@/lib/api";
import { cn, fileDir, fileName, formatScore } from "@/lib/utils";

interface SourceListProps {
  chunks: Chunk[];
  onOpen: (index: number) => void;
}

/**
 * The evidence rail: what the answer was actually written from, in rank order.
 *
 * This is not a list of links appended after the prose — it is the claim the
 * product makes, so it sits beside the answer at all times on a wide screen.
 * Rank is printed because rank is what the prompt gave the model, and each
 * row carries its relevance score as a short bar: five rows of numbers are
 * hard to compare, five bars are not.
 */
export function SourceList({ chunks, onOpen }: SourceListProps) {
  if (chunks.length === 0) return null;

  // Scores mean different things depending on the pipeline (a 1–5 LLM rating
  // when the reranker ran, a small RRF score otherwise), so the bars are
  // scaled against the best score in this set rather than an absolute range.
  const best = Math.max(...chunks.map((chunk) => chunk.score), 0.0001);

  return (
    <section aria-label="Sources" className="min-w-0">
      <header className="mb-2 flex items-baseline justify-between gap-2">
        <h3 className="eyebrow">Evidence</h3>
        <p className="text-[0.6875rem] text-moon-3">
          {chunks.length} chunk{chunks.length === 1 ? "" : "s"}
        </p>
      </header>

      <ul className="space-y-1">
        {chunks.map((chunk, index) => (
          <li key={`${chunk.file_path}:${chunk.start_line}:${index}`}>
            <button
              type="button"
              onClick={() => onOpen(index)}
              className={cn(
                "group grid w-full grid-cols-[1.25rem_1fr] gap-2.5 rounded-control border border-rule bg-panel px-2.5 py-2 text-left",
                "transition-colors hover:border-lamp-line hover:bg-panel-2",
              )}
            >
              <span
                aria-hidden
                className="tally pt-px text-right text-[0.8125rem] leading-5 text-moon-3 group-hover:text-lamp"
              >
                {index + 1}
              </span>

              <span className="min-w-0">
                <span className="flex items-baseline gap-2">
                  <span className="truncate font-mono text-xs text-moon">{chunk.name}</span>
                  <span className="tally ml-auto shrink-0 text-[0.6875rem] text-moon-2">
                    {formatScore(chunk.score)}
                  </span>
                </span>

                <span className="mt-0.5 block truncate font-mono text-[0.6875rem] text-moon-3">
                  {fileDir(chunk.file_path) ? `${fileDir(chunk.file_path)}/` : ""}
                  {fileName(chunk.file_path)}:{chunk.start_line}
                </span>

                <span className="mt-1.5 flex h-0.5 w-full overflow-hidden rounded-pill bg-panel-2">
                  <span
                    className="h-full rounded-pill bg-keep/70 transition-[width] duration-500"
                    style={{ width: `${Math.max(4, (chunk.score / best) * 100)}%` }}
                  />
                </span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
