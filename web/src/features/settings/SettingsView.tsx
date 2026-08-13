import { CheckCircle2, Info, RotateCcw, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Field, Slider, TextInput, Toggle } from "@/components/ui/Field";
import { useToast } from "@/components/ui/Toast";
import { useHealth } from "@/hooks/useHealth";
import { usePipelineSettings } from "@/hooks/useSettings";
import { formatCount } from "@/lib/utils";

/** min_score is optional; the slider's lowest stop means "keep everything". */
const MIN_SCORE_OFF = 0;

export function SettingsView() {
  const toast = useToast();
  const { health } = useHealth();
  const { settings, update, reset } = usePipelineSettings();

  const defaults = health?.defaults;
  const value = <K extends keyof typeof settings>(key: K) =>
    (settings[key] ?? defaults?.[key]) as NonNullable<(typeof settings)[K]>;

  const rerank = (settings.rerank ?? defaults?.rerank ?? true) as boolean;
  const crag = (settings.crag ?? defaults?.crag ?? true) as boolean;
  const minScore = settings.min_score ?? defaults?.min_score ?? null;

  const changed = Object.keys(settings).length > 0;

  return (
    <div className="h-full overflow-y-auto">
      <header className="mx-auto flex w-full max-w-5xl flex-wrap items-end gap-3 px-4 pt-8 sm:px-6">
        <div>
          <p className="eyebrow">Settings</p>
          <h1 className="display mt-2 text-[1.5rem] font-bold leading-tight tracking-[-0.015em] text-moon">
            How hard retrieval works
          </h1>
          <p className="mt-1.5 text-[0.8125rem] text-moon-2">
            Applied to the next question. Stored in this browser, not on the server.
          </p>
        </div>
        {changed && (
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto"
            onClick={() => {
              reset();
              toast.info("Settings restored to the server defaults.");
            }}
          >
            <RotateCcw aria-hidden className="size-3.5" />
            Reset to defaults
          </Button>
        )}
      </header>

      <div className="mx-auto grid w-full max-w-5xl gap-4 px-4 py-6 sm:px-6 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Retrieval"
            description="How many chunks are searched, fused and handed to the model."
          />
          <CardBody className="space-y-6">
            <Slider
              label="Chunks in the answer prompt"
              value={value("top_k") as number}
              min={1}
              max={15}
              onChange={(next) => update("top_k", next)}
              hint="More context can raise recall, but every extra chunk is also a chance for the model to cite something irrelevant."
            />
            <Slider
              label="Candidates fetched before reranking"
              value={value("candidate_k") as number}
              min={5}
              max={30}
              onChange={(next) => update("candidate_k", next)}
              hint="A wider net gives the reranker more to choose from, at the cost of more tokens per question."
            />
            <Slider
              label="RRF constant"
              value={value("rrf_k") as number}
              min={10}
              max={200}
              step={10}
              onChange={(next) => update("rrf_k", next)}
              hint="Controls how sharply reciprocal rank fusion favours top-ranked hits. Lower values trust the first few results more."
            />
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Reranking and correction"
            description="The two LLM passes that run before an answer is written."
          />
          <CardBody className="space-y-6">
            <Toggle
              checked={rerank}
              onChange={(next) => update("rerank", next)}
              label="LLM reranker"
              description="Scores each candidate 1–5 for relevance and keeps the best. Turning it off falls back to raw RRF order — faster and cheaper, noticeably noisier."
            />

            <Slider
              label="Minimum relevance score"
              value={minScore ?? MIN_SCORE_OFF}
              min={MIN_SCORE_OFF}
              max={5}
              step={0.5}
              onChange={(next) => update("min_score", next === MIN_SCORE_OFF ? null : next)}
              display={minScore === null ? "off" : `${minScore}/5`}
              hint="Drops reranked chunks rated below this. Off means always fill the prompt to the chunk count above, even with weak matches."
            />

            <Toggle
              checked={crag}
              onChange={(next) => update("crag", next)}
              label="Corrective RAG"
              description="Grades the retrieval, rewrites the question and retrieves again when it is weak, and drops chunks graded irrelevant. Costs one or two extra LLM calls per question."
            />
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Model" description="The Groq model used for every LLM call." />
          <CardBody>
            <Field
              label="Model id"
              hint="Reranking, grading, rewriting and the final answer all use this model."
            >
              {({ id, describedBy }) => (
                <TextInput
                  id={id}
                  aria-describedby={describedBy}
                  spellCheck={false}
                  value={(value("model") as string) ?? ""}
                  placeholder={defaults?.model}
                  onChange={(event) => update("model", event.target.value || undefined)}
                  className="font-mono text-[0.8125rem]"
                />
              )}
            </Field>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Server" description="Read from the server's environment." />
          <CardBody className="space-y-3 text-[0.8125rem]">
            <Row label="Version" value={health ? `v${health.version}` : "…"} />
            <Row label="Storage" value={health?.storage ?? "…"} mono />
            <Row label="Default collection" value={health?.default_collection ?? "…"} mono />
            <Row label="Default model" value={health?.default_model ?? "…"} mono />
            <Row
              label="Indexed chunks"
              value={
                health ? formatCount(health.collections.reduce((n, c) => n + c.points, 0)) : "…"
              }
            />
            <div className="flex items-center justify-between gap-3 pt-1">
              <span className="text-moon-2">API keys</span>
              {health && health.missing_keys.length === 0 ? (
                <Badge tone="keep" icon={CheckCircle2}>
                  Configured
                </Badge>
              ) : (
                <Badge tone="cut" icon={XCircle}>
                  {health ? `Missing ${health.missing_keys.join(", ")}` : "Unknown"}
                </Badge>
              )}
            </div>

            {/* The icon and the text are the two flex items. Putting the text
                directly in a flex container would make every run of text
                around the inline <code> its own item, laying the sentence out
                in columns. */}
            <div className="flex items-start gap-2 rounded-control border border-rule bg-panel px-3 py-2">
              <Info aria-hidden className="mt-0.5 size-3.5 shrink-0 text-moon-3" />
              <p className="text-xs leading-relaxed text-moon-2">
                Keys and storage come from the server's{" "}
                <code className="font-mono text-moon">.env</code>. Change them there and restart —
                they are deliberately not editable from the browser.
              </p>
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="shrink-0 text-moon-2">{label}</span>
      <span className={mono ? "truncate font-mono text-xs text-moon" : "text-moon"}>{value}</span>
    </div>
  );
}
