import { motion, useReducedMotion } from "framer-motion";
import type { Chunk } from "@/lib/api";
import { cn, fileDir, fileName, formatScore } from "@/lib/utils";

interface SourceListProps {
  chunks: Chunk[];
  /** Which chunk has its drawer open — the row wears the lamp. */
  selected?: number | null;
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
export function SourceList({ chunks, selected = null, onOpen }: SourceListProps) {
  const reduced = useReducedMotion();
  if (chunks.length === 0) return null;

  // Scores mean different things depending on the pipeline (a 1–5 LLM rating
  // when the reranker ran, a small RRF score otherwise), so the bars are
  // scaled against the best score in this set rather than an absolute range.
  const best = Math.max(...chunks.map((chunk) => chunk.score), 0.0001);

  return (
    <section aria-label="Sources" className="min-w-0">
      <header className="mb-2 flex items-baseline justify-between gap-2">
        <h3 className="eyebrow flex items-center gap-2">
          <span aria-hidden className="size-1 rounded-pill bg-lamp" />
          Evidence
        </h3>
        <p className="text-[0.6875rem] text-moon-3">
          {chunks.length} chunk{chunks.length === 1 ? "" : "s"}
        </p>
      </header>

      <ul className="space-y-1">
        {chunks.map((chunk, index) => {
          const active = selected === index;
          return (
            <motion.li
              key={`${chunk.file_path}:${chunk.start_line}:${index}`}
              initial={reduced ? false : { opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25, delay: index * 0.04, ease: "easeOut" }}
            >
              <button
                type="button"
                aria-pressed={active}
                onClick={() => onOpen(index)}
                className={cn(
                  "group relative grid w-full grid-cols-[1.5rem_1fr] gap-2.5 overflow-hidden rounded-control border px-2.5 py-2 text-left transition-colors duration-150",
                  active
                    ? "border-lamp-line bg-panel-2"
                    : "border-rule bg-panel hover:border-lamp-line hover:bg-panel-2",
                )}
              >
                {/* The lamp rail: a hairline that appears on hover and stays
                    for the chunk whose drawer is open. */}
                <span
                  aria-hidden
                  className={cn(
                    "absolute inset-y-1 left-0 w-0.5 rounded-pill bg-lamp transition-opacity duration-150",
                    active ? "opacity-100" : "opacity-0 group-hover:opacity-60",
                  )}
                />
                <span
                  aria-hidden
                  className={cn(
                    "tally pt-px text-right text-[0.8125rem] leading-5 transition-colors",
                    active ? "text-lamp" : "text-moon-3 group-hover:text-lamp",
                  )}
                >
                  {String(index + 1).padStart(2, "0")}
                </span>

                <span className="min-w-0">
                  <span className="flex items-baseline gap-2">
                    <span className="truncate font-mono text-xs text-moon">{chunk.name}</span>
                    <span className="tally ml-auto shrink-0 text-[0.6875rem] text-moon-2">
                      {formatScore(chunk.score)}
                    </span>
                  </span>

                  <span
                    title={chunk.file_path}
                    className="mt-0.5 block truncate font-mono text-[0.6875rem] text-moon-3"
                  >
                    {fileDir(chunk.file_path) ? `${fileDir(chunk.file_path)}/` : ""}
                    {fileName(chunk.file_path)}:{chunk.start_line}
                  </span>

                  <span className="mt-1.5 flex h-1 w-full overflow-hidden rounded-pill bg-panel-2">
                    <span
                      className={cn(
                        "h-full rounded-pill transition-[width,background-color] duration-500",
                        active ? "bg-lamp" : "bg-keep/70",
                      )}
                      style={{ width: `${Math.max(4, (chunk.score / best) * 100)}%` }}
                    />
                  </span>
                </span>
              </button>
            </motion.li>
          );
        })}
      </ul>
    </section>
  );
}
