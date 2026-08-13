import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowUp, Square } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";

interface ComposerProps {
  busy: boolean;
  disabled: boolean;
  placeholder: string;
  /** Rendered on the footer line — the corpus this question will be asked of. */
  target?: ReactNode;
  onSubmit: (question: string) => void;
  onStop: () => void;
}

const MAX_HEIGHT_PX = 200;

export function Composer({
  busy,
  disabled,
  placeholder,
  target,
  onSubmit,
  onStop,
}: ComposerProps) {
  const [value, setValue] = useState("");
  const textarea = useRef<HTMLTextAreaElement>(null);

  // Grow with the question, up to a cap — a long question should be readable
  // without turning the composer into the whole screen.
  useEffect(() => {
    const element = textarea.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, MAX_HEIGHT_PX)}px`;
  }, [value]);

  const submit = () => {
    const question = value.trim();
    if (!question || busy || disabled) return;
    onSubmit(question);
    setValue("");
  };

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
      className="border-t border-rule bg-nav px-4 py-3 sm:px-6"
    >
      <div className="mx-auto w-full max-w-5xl">
        <div
          className={cn(
            "flex items-end gap-2 rounded-panel border bg-ink p-2 transition-all duration-200",
            disabled
              ? "border-rule opacity-60"
              : "border-rule focus-within:border-lamp-line focus-within:shadow-[0_0_0_3px_rgba(255,180,84,0.12),var(--glow-lamp)]",
          )}
        >
          <label htmlFor="question" className="sr-only">
            Your question about the codebase
          </label>
          <textarea
            id="question"
            ref={textarea}
            rows={1}
            value={value}
            disabled={disabled}
            placeholder={placeholder}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={(event) => {
              // Enter sends, Shift+Enter breaks the line — the convention every
              // chat interface has trained users on.
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                submit();
              }
            }}
            className={cn(
              "max-h-[12.5rem] min-h-[2.5rem] flex-1 resize-none bg-transparent px-2.5 py-2",
              "text-sm leading-relaxed text-moon placeholder:text-moon-3",
              "focus:outline-none disabled:cursor-not-allowed",
            )}
          />

          {/* AnimatePresence crossfades between Send and Stop so the swap
              reads as a smooth state change, not a hard cut. */}
          <AnimatePresence mode="wait" initial={false}>
            {busy ? (
              <motion.span
                key="stop"
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }}
                transition={{ duration: 0.12 }}
              >
                <Button variant="secondary" size="sm" onClick={onStop} aria-label="Stop generating">
                  <Square aria-hidden className="size-3" fill="currentColor" />
                  Stop
                </Button>
              </motion.span>
            ) : (
              <motion.span
                key="send"
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }}
                transition={{ duration: 0.12 }}
              >
                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  iconOnly
                  disabled={disabled || !value.trim()}
                  aria-label="Ask question"
                  // The send button lifts and the arrow rises with it — one small
                  // beat when the question is ready to go, then it is gone.
                  className="group h-9 w-9 transition-[background-color,box-shadow,transform] duration-150 hover:-translate-y-px hover:shadow-[0_6px_16px_-6px_rgba(255,180,84,0.65)] [&>svg]:transition-transform [&>svg]:duration-150 group-hover:[&>svg]:-translate-y-0.5"
                >
                  <ArrowUp aria-hidden className="size-4" />
                </Button>
              </motion.span>
            )}
          </AnimatePresence>
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
          {target}
          <p className="ml-auto hidden text-[0.6875rem] text-moon-3 sm:block">
            <kbd className="rounded-[0.25rem] border border-rule bg-panel-2 px-1 font-mono text-[0.625rem]">
              Enter
            </kbd>{" "}
            asks ·{" "}
            <kbd className="rounded-[0.25rem] border border-rule bg-panel-2 px-1 font-mono text-[0.625rem]">
              Shift + Enter
            </kbd>{" "}
            new line
          </p>
        </div>
        {/* The keyboard hints sit on bg-nav; the kbd backgrounds need to match. */}
      </div>
    </form>
  );
}
