import { useCallback, useEffect, useRef, useState } from "react";
import { Database, RefreshCw, Trash2 } from "lucide-react";
import { api, ApiError, type Job } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonRows } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { useHealth } from "@/hooks/useHealth";
import { formatCount } from "@/lib/utils";
import { IngestPanel } from "./IngestPanel";
import { JobPanel } from "./JobPanel";

// While a run is in flight the log should feel live; when nothing is running
// there is nothing to see, so back right off instead of polling an idle server
// fifty times a minute.
const POLL_ACTIVE_MS = 1200;
const POLL_IDLE_MS = 10000;

export function CorpusView() {
  const toast = useToast();
  const { health, loading, refresh } = useHealth();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobsLoading, setJobsLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);

  // Tracks whether the last poll saw work in flight, so the collection list is
  // refreshed exactly once when the last run finishes rather than every tick.
  const wasActive = useRef(false);
  const [active, setActive] = useState(false);

  const poll = useCallback(async () => {
    try {
      const next = await api.jobs();
      setJobs(next);
      const running = next.some((job) => job.status === "running" || job.status === "queued");
      if (wasActive.current && !running) void refresh();
      wasActive.current = running;
      setActive(running);
    } catch {
      // A failed poll is not worth a toast — the next tick will retry, and the
      // server-unreachable case already panels on the health banner.
    } finally {
      setJobsLoading(false);
    }
  }, [refresh]);

  useEffect(() => {
    void poll();
    const timer = window.setInterval(poll, active ? POLL_ACTIVE_MS : POLL_IDLE_MS);
    return () => window.clearInterval(timer);
  }, [poll, active]);

  const remove = async (name: string) => {
    if (!window.confirm(`Delete the collection "${name}"? Its indexed chunks are removed permanently.`)) {
      return;
    }
    setDeleting(name);
    try {
      await api.deleteCollection(name);
      toast.success(`Deleted "${name}".`);
      await refresh();
    } catch (caught) {
      toast.error(caught instanceof ApiError ? caught.message : `Could not delete "${name}".`);
    } finally {
      setDeleting(null);
    }
  };

  const collections = health?.collections ?? [];

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto w-full max-w-5xl px-4 pt-8 sm:px-6">
        {/* No full-bleed page header: the top bar already names where you are
            and how much is indexed. What belongs here is the one fact it does
            not carry — where the index physically lives. */}
        <p className="eyebrow">Corpus</p>
        <h1 className="display mt-2 text-[1.5rem] font-bold leading-tight tracking-[-0.015em] text-moon">
          What NightRag can answer from
        </h1>
        <p className="mt-1.5 text-[0.8125rem] text-moon-2">
          Stored in <span className="font-mono text-moon">{health?.storage ?? "…"}</span>
        </p>
      </div>

      <div className="mx-auto grid w-full max-w-5xl gap-4 px-4 py-6 sm:px-6 lg:grid-cols-2">
        <div className="space-y-4">
          <IngestPanel
            defaultCollection={health?.default_collection ?? "code_chunks"}
            onStarted={(job) => {
              setJobs((current) => [job, ...current]);
              // Switch to the fast cadence now rather than waiting up to ten
              // seconds for the idle poll to notice the new run.
              setActive(true);
            }}
          />
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader
              title="Collections"
              description="Each holds the chunks of one or more ingested codebases."
              action={
                <Button size="sm" variant="ghost" onClick={() => void refresh()} disabled={loading}>
                  <RefreshCw aria-hidden className="size-3.5" />
                  Refresh
                </Button>
              }
            />
            <CardBody className="pt-0">
              {loading && collections.length === 0 ? (
                <SkeletonRows rows={2} />
              ) : collections.length === 0 ? (
                <EmptyState
                  icon={Database}
                  title="Nothing indexed yet"
                  description="Add a folder, a Git repository or a .zip and its Python files become searchable."
                  className="py-10"
                />
              ) : (
                <ul className="space-y-2">
                  {collections.map((collection) => (
                    <li
                      key={collection.name}
                      className="flex items-center gap-3 rounded-control border border-rule bg-panel p-3"
                    >
                      {/* Neutral: the lamp means live or selected, and every
                          collection wearing it would spend the accent on decoration. */}
                      <span
                        aria-hidden
                        className="flex size-7 shrink-0 items-center justify-center rounded-control border border-rule bg-panel text-moon-3"
                      >
                        <Database className="size-3.5" />
                      </span>

                      <div className="min-w-0 flex-1">
                        <p className="truncate font-mono text-[0.8125rem] text-moon">
                          {collection.name}
                        </p>
                        <p className="mt-0.5 text-[0.6875rem] text-moon-3">
                          {formatCount(collection.points)} chunks
                          {collection.vector_size ? ` · ${collection.vector_size}-dim vectors` : ""}
                        </p>
                      </div>

                      {collection.indexed && <Badge tone="keep">BM25 warm</Badge>}

                      <Button
                        size="sm"
                        variant="ghost"
                        iconOnly
                        loading={deleting === collection.name}
                        onClick={() => void remove(collection.name)}
                        aria-label={`Delete collection ${collection.name}`}
                        className="hover:text-cut"
                      >
                        <Trash2 aria-hidden className="size-4" />
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </CardBody>
          </Card>

          <JobPanel jobs={jobs} loading={jobsLoading} />
        </div>
      </div>
    </div>
  );
}
