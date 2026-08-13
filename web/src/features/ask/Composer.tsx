import { useEffect, useRef, useState } from "react";
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
      className="border-t border-rule bg-panel px-4 py-3 sm:px-6"
    >
      <div className="mx-auto w-full max-w-5xl">
        <div
          className={cn(
            "flex items-end gap-2 rounded-panel border bg-ink p-2 transition-colors",
            disabled ? "border-rule opacity-60" : "border-rule focus-within:border-lamp-line",
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
              "max-h-[12.5rem] min-h-[2.25rem] flex-1 resize-none bg-transparent px-2 py-1.5",
              "text-sm leading-relaxed text-moon placeholder:text-moon-3",
              "focus:outline-none disabled:cursor-not-allowed",
            )}
          />

          {busy ? (
            <Button variant="secondary" size="sm" onClick={onStop} aria-label="Stop generating">
              <Square aria-hidden className="size-3" fill="currentColor" />
              Stop
            </Button>
          ) : (
            <Button
              type="submit"
              variant="primary"
              size="sm"
              iconOnly
              disabled={disabled || !value.trim()}
              aria-label="Ask question"
            >
              <ArrowUp aria-hidden className="size-4" />
            </Button>
          )}
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
          {target}
          <p className="ml-auto text-[0.6875rem] text-moon-3">
            <kbd className="rounded-[0.25rem] border border-rule bg-panel-2 px-1 font-mono">
              Enter
            </kbd>{" "}
            asks ·{" "}
            <kbd className="rounded-[0.25rem] border border-rule bg-panel-2 px-1 font-mono">
              Shift + Enter
            </kbd>{" "}
            new line
          </p>
        </div>
      </div>
    </form>
  );
}
