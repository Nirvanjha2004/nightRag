import { useEffect, useRef, useState } from "react";
import { ArrowUp, Square } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";

interface ComposerProps {
  busy: boolean;
  disabled: boolean;
  placeholder: string;
  onSubmit: (question: string) => void;
  onStop: () => void;
}

const MAX_HEIGHT_PX = 200;

export function Composer({ busy, disabled, placeholder, onSubmit, onStop }: ComposerProps) {
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
      className="border-t border-line bg-surface/80 px-4 py-3 backdrop-blur-sm sm:px-6"
    >
      <div
        className={cn(
          "mx-auto flex w-full max-w-3xl items-end gap-2 rounded-card border bg-surface-raised p-2",
          "transition-colors focus-within:border-accent",
          disabled ? "border-line opacity-60" : "border-line hover:border-line-strong",
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
            "text-sm leading-relaxed text-fg placeholder:text-fg-subtle",
            "focus:outline-none disabled:cursor-not-allowed",
          )}
        />

        {busy ? (
          <Button variant="secondary" size="sm" onClick={onStop} aria-label="Stop generating">
            <Square aria-hidden className="size-3.5" fill="currentColor" />
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

      <p className="mx-auto mt-2 max-w-3xl text-[0.6875rem] text-fg-subtle">
        <kbd className="rounded-[0.25rem] border border-line bg-surface-hover px-1 font-mono">Enter</kbd>{" "}
        to ask ·{" "}
        <kbd className="rounded-[0.25rem] border border-line bg-surface-hover px-1 font-mono">
          Shift + Enter
        </kbd>{" "}
        for a new line
      </p>
    </form>
  );
}
