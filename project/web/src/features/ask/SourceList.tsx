import { FileCode2 } from "lucide-react";
import type { Chunk } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { cn, fileDir, fileName, formatScore } from "@/lib/utils";

interface SourceListProps {
  chunks: Chunk[];
  onOpen: (index: number) => void;
}

/**
 * The chunks the answer was grounded on.
 *
 * Rank is shown explicitly (`[1]`, `[2]`) because it is what the prompt gives
 * the model — the answer's citations refer to these numbers.
 */
export function SourceList({ chunks, onOpen }: SourceListProps) {
  if (chunks.length === 0) return null;

  return (
    <section aria-label="Sources" className="space-y-2">
      <h3 className="text-[0.6875rem] font-semibold uppercase tracking-wider text-fg-subtle">
        Grounded on {chunks.length} chunk{chunks.length === 1 ? "" : "s"}
      </h3>
      <ul className="grid gap-1.5 sm:grid-cols-2">
        {chunks.map((chunk, index) => (
          <li key={`${chunk.file_path}:${chunk.start_line}:${index}`}>
            <button
              type="button"
              onClick={() => onOpen(index)}
              className={cn(
                "group flex w-full items-start gap-2.5 rounded-control border border-line bg-surface p-2.5 text-left",
                "transition-colors hover:border-line-strong hover:bg-surface-hover",
              )}
            >
              <span
                aria-hidden
                className="mt-px flex size-5 shrink-0 items-center justify-center rounded-[0.3rem] bg-surface-hover font-mono text-[0.625rem] text-fg-subtle"
              >
                {index + 1}
              </span>

              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5">
                  <FileCode2 aria-hidden className="size-3.5 shrink-0 text-fg-subtle" />
                  <span className="truncate font-mono text-xs text-fg group-hover:text-accent">
                    {fileName(chunk.file_path)}
                  </span>
                </span>
                <span className="mt-1 block truncate text-[0.6875rem] text-fg-subtle">
                  {chunk.name} · lines {chunk.start_line}–{chunk.end_line}
                  {fileDir(chunk.file_path) && ` · ${fileDir(chunk.file_path)}`}
                </span>
              </span>

              <Badge tone="neutral" className="shrink-0">
                {formatScore(chunk.score)}
              </Badge>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
