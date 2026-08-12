import { useEffect, useMemo, useRef } from "react";
import { Link } from "react-router-dom";
import { Database, KeyRound, Trash2 } from "lucide-react";
import { Button, buttonClasses } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { useHealth } from "@/hooks/useHealth";
import { usePipelineSettings } from "@/hooks/useSettings";
import { cn, formatCount } from "@/lib/utils";
import { Composer } from "./Composer";
import { Turn } from "./Turn";
import { useAsk } from "./useAsk";

const EXAMPLES = [
  "Where is the retry-with-backoff logic defined?",
  "How are chunks deduplicated when two retrievers return the same one?",
  "What happens when the reranker's response cannot be parsed?",
];

export function AskView() {
  const { health, loading, refresh } = useHealth();
  const { settings, update } = usePipelineSettings();
  const bottom = useRef<HTMLDivElement>(null);

  const collections = health?.collections ?? [];
  const collection = settings.collection ?? health?.default_collection ?? "";
  const missingKeys = health?.missing_keys ?? [];
  const blocked = loading || missingKeys.length > 0 || collections.length === 0;

  const options = useMemo(
    () => ({ ...settings, collection: collection || undefined }),
    [settings, collection],
  );
  const { turns, busy, ask, stop, clear } = useAsk(options);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length]);

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6">
          {turns.length === 0 ? (
            <Opening
              loading={loading}
              missingKeys={missingKeys}
              hasCollections={collections.length > 0}
              disabled={blocked}
              onRetry={refresh}
              onExample={ask}
            />
          ) : (
            <div className="space-y-8">
              {turns.map((turn) => (
                <Turn key={turn.id} turn={turn} />
              ))}
              <div className="flex justify-center pb-2">
                <Button size="sm" variant="ghost" onClick={clear}>
                  <Trash2 aria-hidden className="size-3.5" />
                  Clear conversation
                </Button>
              </div>
            </div>
          )}
          <div ref={bottom} />
        </div>
      </div>

      <Composer
        busy={busy}
        disabled={blocked}
        placeholder={blocked ? "Finish setup to start asking" : "Ask about the indexed code…"}
        target={
          collections.length > 0 && (
            <label className="flex items-center gap-1.5 text-[0.6875rem] text-moon-3">
              <span className="eyebrow">Asking</span>
              <select
                value={collection}
                onChange={(event) => update("collection", event.target.value)}
                className="rounded-control border border-rule bg-panel px-1.5 py-0.5 font-mono text-[0.6875rem] text-moon-2 transition-colors hover:border-rule-strong focus:border-lamp focus:outline-none"
              >
                {collections.map((item) => (
                  <option key={item.name} value={item.name}>
                    {item.name} · {formatCount(item.points)}
                  </option>
                ))}
              </select>
            </label>
          )
        }
        onSubmit={ask}
        onStop={stop}
      />
    </div>
  );
}

interface OpeningProps {
  loading: boolean;
  missingKeys: string[];
  hasCollections: boolean;
  disabled: boolean;
  onRetry: () => void;
  onExample: (question: string) => void;
}

/**
 * The opening screen states the thesis rather than greeting the reader.
 *
 * What is characteristic about this product is not that you can ask it things
 * — everything can be asked things — it is that retrieval throws most of the
 * codebase away on the way to an answer, and shows you the discards. So the
 * hero is the funnel at rest: the shape a question is about to be put through.
 */
function Opening({
  loading,
  missingKeys,
  hasCollections,
  disabled,
  onRetry,
  onExample,
}: OpeningProps) {
  if (loading) {
    return (
      <div className="py-20 text-center">
        <p className="eyebrow">Connecting</p>
        <p className="mt-2 text-sm text-moon-2">Reading the server's collections.</p>
      </div>
    );
  }

  if (missingKeys.length > 0) {
    return (
      <EmptyState
        icon={KeyRound}
        tone="cut"
        title="API keys are missing"
        description={
          <>
            Add{" "}
            {missingKeys.map((key, index) => (
              <span key={key}>
                {index > 0 && " and "}
                <code className="font-mono text-moon">{key}</code>
              </span>
            ))}{" "}
            to your <code className="font-mono text-moon">.env</code> file and restart the server.
            Copy <code className="font-mono text-moon">.env.example</code> to get started.
          </>
        }
        action={
          <Button variant="secondary" onClick={onRetry}>
            Check again
          </Button>
        }
      />
    );
  }

  if (!hasCollections) {
    return (
      <EmptyState
        icon={Database}
        title="Nothing indexed yet"
        description="Point NightRag at a folder, a public Git repository or a .zip. Every Python file under it is split by function, class and method, then embedded."
        action={
          <Link to="/corpus" className={buttonClasses({ variant: "primary" })}>
            Add a codebase
          </Link>
        }
      />
    );
  }

  return (
    // Centred in whatever height is left over: the opening screen is a
    // statement, and leaving it stranded against the top rail with an empty
    // half-screen beneath reads as an unfinished page rather than a composed one.
    <div className="grid min-h-[calc(100dvh-14rem)] content-center gap-10 py-6 lg:grid-cols-[minmax(0,1fr)_20rem] lg:items-center lg:gap-14">
      <div className="min-w-0">
        <p className="eyebrow">Retrieval-grounded code search</p>
        <h1 className="display mt-3 text-[2.25rem] font-bold leading-[1.05] tracking-[-0.02em] text-moon sm:text-[2.75rem]">
          Every answer is
          <br />
          what survived.
        </h1>
        <p className="mt-4 max-w-md text-[0.9375rem] leading-relaxed text-moon-2">
          A question goes out to two retrievers at once. Their results are fused, scored one by one
          by a language model, graded, and — when the grade is poor — thrown out and asked again.
          Whatever is left writes the answer. You get to see everything that did not make it.
        </p>

        <p className="eyebrow mt-10">Start with</p>
        <ul className="mt-2.5 space-y-px">
          {EXAMPLES.map((example) => (
            <li key={example}>
              <button
                type="button"
                disabled={disabled}
                onClick={() => onExample(example)}
                className={cn(
                  "group flex w-full items-baseline gap-3 border-b border-rule py-2.5 text-left",
                  "text-[0.875rem] text-moon-2 transition-colors",
                  "hover:border-lamp-line hover:text-moon disabled:cursor-not-allowed disabled:opacity-50",
                )}
              >
                <span className="min-w-0 flex-1">{example}</span>
                <span
                  aria-hidden
                  className="eyebrow shrink-0 text-lamp/70 transition-colors group-hover:text-lamp"
                >
                  Ask →
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>

      <RestingLadder />
    </div>
  );
}

/**
 * The signature, at rest: the shape of the cull before any question is asked.
 * Widths are illustrative of a typical run, not live data — which is why the
 * numbers are absent and the bars are drawn in the quiet rule colour.
 */
function RestingLadder() {
  const shape = [
    { label: "Searched", width: 100, note: "dense + BM25, in parallel" },
    { label: "Fused", width: 74, note: "duplicates merged by rank" },
    { label: "Reranked", width: 44, note: "scored 1–5 by the model" },
    { label: "Graded", width: 44, note: "correct, ambiguous, incorrect" },
    { label: "Kept", width: 30, note: "what the answer is written from" },
  ];

  return (
    <aside
      aria-label="How retrieval narrows"
      className="rounded-panel border border-rule bg-panel px-4 py-4 shadow-[var(--shadow-panel)] lg:self-start"
    >
      <h2 className="eyebrow">The cull</h2>
      {/* No 01/02/03 markers: the bars already descend in running order, so a
          number would repeat what the shape says and add nothing. */}
      <ol className="mt-3 space-y-3">
        {shape.map((step) => (
          <li key={step.label}>
            <span className="display text-[0.8125rem] font-semibold text-moon-2">{step.label}</span>
            <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-pill bg-ink">
              <span
                // Steel, not rule: against the panel a hairline-coloured fill
                // reads as an underline rather than a measurement.
                className="block h-full rounded-pill bg-moon-3/60"
                style={{ width: `${step.width}%` }}
              />
            </div>
            <p className="mt-1 text-[0.6875rem] text-moon-3">{step.note}</p>
          </li>
        ))}
      </ol>
    </aside>
  );
}
