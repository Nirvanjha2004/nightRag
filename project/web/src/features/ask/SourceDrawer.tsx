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
            className="fixed inset-0 z-40 bg-canvas/70 backdrop-blur-[2px] lg:hidden"
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
            className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[min(46rem,100vw)] flex-col border-l border-line bg-surface shadow-[-8px_0_32px_rgba(0,0,0,0.3)]"
          >
            <header className="flex items-start gap-3 border-b border-line px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="truncate font-mono text-[0.8125rem] text-fg">{chunk.file_path}</p>
                <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-fg-muted">
                  <span>{chunk.node_type.replace(/_/g, " ")}</span>
                  <span aria-hidden>·</span>
                  <span className="font-mono text-fg">{chunk.name}</span>
                  <span aria-hidden>·</span>
                  <span>
                    lines {chunk.start_line}–{chunk.end_line}
                  </span>
                  <Badge tone="accent">rank {index! + 1}</Badge>
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

            <footer className="flex items-center justify-between gap-3 border-t border-line px-4 py-2.5">
              <span className="text-xs text-fg-muted">
                {index! + 1} of {chunks.length}
              </span>
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
