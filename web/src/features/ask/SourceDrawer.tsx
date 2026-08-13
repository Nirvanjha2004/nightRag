import { useEffect, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronLeft, ChevronRight, Copy, X } from "lucide-react";
import type { Chunk } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { CodeBlock } from "@/components/CodeBlock";
import { useToast } from "@/components/ui/Toast";
import { formatScore } from "@/lib/utils";

interface SourceDrawerProps {
  chunks: Chunk[];
  /** Index into `chunks`, or null when the drawer is closed. */
  index: number | null;
  onClose: () => void;
  onNavigate: (index: number) => void;
}

/** Full text of one retrieved chunk, with the neighbours one keypress away. */
export function SourceDrawer({ chunks, index, onClose, onNavigate }: SourceDrawerProps) {
  const toast = useToast();
  const closeRef = useRef<HTMLButtonElement>(null);
  const open = index !== null && index >= 0 && index < chunks.length;
  const chunk = open ? chunks[index] : null;

  useEffect(() => {
    if (!open) return;

    // Focus moves into the drawer so the keyboard follows the eye, and Escape
    // brings it back out.
    closeRef.current?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key === "ArrowDown" && index! < chunks.length - 1) onNavigate(index! + 1);
      if (event.key === "ArrowUp" && index! > 0) onNavigate(index! - 1);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, index, chunks.length, onClose, onNavigate]);

  const copy = async () => {
    if (!chunk) return;
    try {
      await navigator.clipboard.writeText(chunk.text);
      toast.success("Chunk copied to the clipboard.");
    } catch {
      toast.error("The browser blocked clipboard access.");
    }
  };

  return (
    <AnimatePresence>
      {open && chunk && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={onClose}
            className="fixed inset-0 z-40 bg-ink/70 backdrop-blur-[2px] lg:hidden"
            aria-hidden
          />

          <motion.aside
            role="dialog"
            aria-modal="true"
            aria-label={`Source ${index! + 1}: ${chunk.file_path}`}
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 380, damping: 38 }}
            className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[min(46rem,100vw)] flex-col border-l border-rule bg-panel shadow-[var(--shadow-drawer)]"
          >
            {/* The lamp rail: the drawer is evidence under the lamp's light,
                so it opens with the same accent the row it came from wears. */}
            <span aria-hidden className="h-0.5 w-full shrink-0 bg-lamp" />

            <header className="flex items-start gap-3 border-b border-rule px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="truncate font-mono text-[0.8125rem] text-moon">{chunk.file_path}</p>
                <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-moon-2">
                  <span className="rounded-[0.25rem] border border-rule bg-panel-2 px-1.5 py-0.5 font-mono text-[0.6875rem] text-moon-2">
                    {chunk.node_type.replace(/_/g, " ")}
                  </span>
                  <span className="font-mono text-moon">{chunk.name}</span>
                  <span aria-hidden className="text-moon-3">·</span>
                  <span className="tabular-nums">
                    lines {chunk.start_line}–{chunk.end_line}
                  </span>
                  <Badge tone="lamp">rank {index! + 1}</Badge>
                  <Badge tone="neutral">score {formatScore(chunk.score)}</Badge>
                </p>
              </div>

              <div className="flex shrink-0 items-center gap-1">
                <Button size="sm" variant="ghost" iconOnly onClick={copy} aria-label="Copy chunk">
                  <Copy aria-hidden className="size-4" />
                </Button>
                <Button
                  ref={closeRef}
                  size="sm"
                  variant="ghost"
                  iconOnly
                  onClick={onClose}
                  aria-label="Close source panel"
                >
                  <X aria-hidden className="size-4" />
                </Button>
              </div>
            </header>

            <div className="min-h-0 flex-1 overflow-y-auto p-4">
              <CodeBlock code={chunk.text} startLine={chunk.start_line} />
            </div>

            <footer className="flex items-center justify-between gap-3 border-t border-rule px-4 py-2.5">
              <span className="text-xs text-moon-2">
                <span className="tally tabular-nums text-moon">{index! + 1}</span> of{" "}
                {chunks.length}
              </span>
              <p className="hidden text-[0.6875rem] text-moon-3 md:block">
                <kbd className="rounded-[0.25rem] border border-rule bg-panel-2 px-1 font-mono text-[0.625rem]">↑</kbd>{" "}
                /{" "}
                <kbd className="rounded-[0.25rem] border border-rule bg-panel-2 px-1 font-mono text-[0.625rem]">↓</kbd>{" "}
                navigate ·{" "}
                <kbd className="rounded-[0.25rem] border border-rule bg-panel-2 px-1 font-mono text-[0.625rem]">Esc</kbd>{" "}
                close
              </p>
              <div className="flex gap-1.5">
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={index === 0}
                  onClick={() => onNavigate(index! - 1)}
                >
                  <ChevronLeft aria-hidden className="size-3.5" />
                  Previous
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={index === chunks.length - 1}
                  onClick={() => onNavigate(index! + 1)}
                >
                  Next
                  <ChevronRight aria-hidden className="size-3.5" />
                </Button>
              </div>
            </footer>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
