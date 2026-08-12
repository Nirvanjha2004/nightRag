import { useEffect, useMemo, useRef } from "react";
import { Link } from "react-router-dom";
import { Database, KeyRound, MessagesSquare, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button, buttonClasses } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Select } from "@/components/ui/Field";
import { useHealth } from "@/hooks/useHealth";
import { usePipelineSettings } from "@/hooks/useSettings";
import { formatCount } from "@/lib/utils";
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

  // Follow the conversation as it grows. `block: "end"` keeps the composer in
  // view, so the user never has to scroll back to type.
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length]);

  return (
    <div className="flex h-full flex-col">
      <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-line px-4 py-3 sm:px-6">
        <div className="min-w-0">
          <h1 className="text-sm font-semibold text-fg">Ask</h1>
          <p className="mt-0.5 text-xs text-fg-muted">
            Answers are written only from retrieved code, with every step on the record.
          </p>
        </div>

        <div className="ml-auto flex items-center gap-2">
          {collections.length > 0 && (
            <>
              <label htmlFor="collection" className="sr-only">
                Collection to search
              </label>
              <Select
                id="collection"
                value={collection}
                onChange={(event) => update("collection", event.target.value)}
                className="h-8 w-auto min-w-[9rem] text-xs"
              >
                {collections.map((item) => (
                  <option key={item.name} value={item.name}>
                    {item.name} ({formatCount(item.points)})
                  </option>
                ))}
              </Select>
            </>
          )}
          {turns.length > 0 && (
            <Button size="sm" variant="ghost" onClick={clear}>
              <Trash2 aria-hidden className="size-3.5" />
              Clear
            </Button>
          )}
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6">
          {turns.length === 0 ? (
            <Landing
              loading={loading}
              missingKeys={missingKeys}
              hasCollections={collections.length > 0}
              onRetry={refresh}
              onExample={ask}
              disabled={blocked}
            />
          ) : (
            <div className="space-y-8">
              {turns.map((turn) => (
                <Turn key={turn.id} turn={turn} />
              ))}
            </div>
          )}
          <div ref={bottom} />
        </div>
      </div>

      <Composer
        busy={busy}
        disabled={blocked}
        placeholder={
          blocked ? "Finish setup to start asking questions" : "Ask about the ingested codebase…"
        }
        onSubmit={ask}
        onStop={stop}
      />
    </div>
  );
}

interface LandingProps {
  loading: boolean;
  missingKeys: string[];
  hasCollections: boolean;
  disabled: boolean;
  onRetry: () => void;
  onExample: (question: string) => void;
}

/** Empty, setup-required and ready states all live here — never a blank page. */
function Landing({
  loading,
  missingKeys,
  hasCollections,
  disabled,
  onRetry,
  onExample,
}: LandingProps) {
  if (loading) {
    return (
      <EmptyState
        icon={MessagesSquare}
        title="Connecting to the pipeline"
        description="Reading the server's collections and configuration."
      />
    );
  }

  if (missingKeys.length > 0) {
    return (
      <EmptyState
        icon={KeyRound}
        tone="critical"
        title="API keys are missing"
        description={
          <>
            Add{" "}
            {missingKeys.map((key, index) => (
              <span key={key}>
                {index > 0 && " and "}
                <code className="font-mono text-fg">{key}</code>
              </span>
            ))}{" "}
            to your <code className="font-mono text-fg">.env</code> file and restart the server.
            Copy <code className="font-mono text-fg">.env.example</code> to get started.
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
        title="No codebase ingested yet"
        description="Point NightRag at a folder, a public Git repository or a .zip, and it will chunk, embed and index every Python file it finds."
        action={
          <Link to="/corpus" className={buttonClasses({ variant: "primary" })}>
            Add a codebase
          </Link>
        }
      />
    );
  }

  return (
    <div className="py-10">
      <div className="mb-7 max-w-lg">
        <h2 className="text-lg font-semibold tracking-tight text-fg">
          Ask anything about the code.
        </h2>
        <p className="mt-1.5 text-sm leading-relaxed text-fg-muted">
          Every question runs hybrid retrieval, an LLM reranking pass and a corrective round before
          a single word is generated. The pipeline panel shows exactly what happened.
        </p>
      </div>

      <h3 className="mb-2.5 text-[0.6875rem] font-semibold uppercase tracking-wider text-fg-subtle">
        Try one of these
      </h3>
      <ul className="space-y-1.5">
        {EXAMPLES.map((example) => (
          <li key={example}>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onExample(example)}
              className="w-full rounded-control border border-line bg-surface px-3.5 py-2.5 text-left text-[0.8125rem] text-fg-muted transition-colors hover:border-line-strong hover:bg-surface-hover hover:text-fg disabled:cursor-not-allowed disabled:opacity-60"
            >
              {example}
            </button>
          </li>
        ))}
      </ul>

      <p className="mt-6 flex flex-wrap items-center gap-1.5 text-xs text-fg-subtle">
        <Badge tone="neutral">hybrid BM25 + dense</Badge>
        <Badge tone="neutral">RRF fusion</Badge>
        <Badge tone="neutral">LLM reranking</Badge>
        <Badge tone="neutral">corrective RAG</Badge>
      </p>
    </div>
  );
}
