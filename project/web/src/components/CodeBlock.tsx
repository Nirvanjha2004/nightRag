import { useMemo } from "react";
import hljs from "highlight.js/lib/core";
import python from "highlight.js/lib/languages/python";
import { cn } from "@/lib/utils";

// Only Python is registered: the chunker parses Python, so every chunk the
// pipeline can return is Python. Registering the full bundle would add
// hundreds of kilobytes to serve grammars nothing renders.
hljs.registerLanguage("python", python);

/**
 * Split highlight.js output into one HTML string per line, keeping every line
 * balanced.
 *
 * A naive `html.split("\n")` tears spans in half whenever a token covers more
 * than one line — exactly what a Python docstring does — leaving the rest of
 * the chunk mis-coloured. So open tags are closed at each line break and
 * reopened on the next line. highlight.js only ever emits `<span>`, which is
 * what makes the fixed closing tag safe.
 */
function splitHighlightedLines(html: string): string[] {
  const lines: string[] = [];
  const open: string[] = [];
  let current = "";

  for (const [token] of html.matchAll(/<[^>]+>|[^<]+/g)) {
    if (token.startsWith("<")) {
      if (token.startsWith("</")) open.pop();
      else if (!token.endsWith("/>")) open.push(token);
      current += token;
      continue;
    }

    const parts = token.split("\n");
    parts.forEach((part, index) => {
      if (index > 0) {
        lines.push(current + "</span>".repeat(open.length));
        current = open.join("");
      }
      current += part;
    });
  }

  lines.push(current + "</span>".repeat(open.length));
  return lines;
}

interface CodeBlockProps {
  code: string;
  /** Line number the first line of `code` came from in its source file. */
  startLine?: number;
  className?: string;
}

export function CodeBlock({ code, startLine, className }: CodeBlockProps) {
  const lines = useMemo(() => {
    // Highlight the whole block once, then split: highlighting line by line
    // would break docstrings and multi-line strings.
    const highlighted = hljs.highlight(code, { language: "python", ignoreIllegals: true }).value;
    return splitHighlightedLines(highlighted);
  }, [code]);

  return (
    <div
      className={cn(
        "overflow-x-auto rounded-control border border-rule bg-ink font-mono text-[0.78125rem] leading-[1.65]",
        className,
      )}
    >
      <pre className="min-w-full py-2.5">
        <code className="hljs block">
          {lines.map((line, index) => (
            <span key={index} className="flex">
              {startLine !== undefined && (
                <span
                  aria-hidden
                  className="sticky left-0 mr-4 w-11 shrink-0 select-none bg-ink pr-2 text-right text-moon-3/70 tabular-nums"
                >
                  {startLine + index}
                </span>
              )}
              <span
                className="min-w-0 flex-1 whitespace-pre pr-4"
                dangerouslySetInnerHTML={{ __html: line || " " }}
              />
            </span>
          ))}
        </code>
      </pre>
    </div>
  );
}
