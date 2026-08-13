import { useEffect, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, FileArchive, FolderOpen, GitBranch, Loader2, XCircle } from "lucide-react";
import type { Job } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { cn, formatCount, formatTime } from "@/lib/utils";

const SOURCE_ICON = {
  path: FolderOpen,
  git: GitBranch,
  upload: FileArchive,
} as const;

const STATUS = {
  queued: { tone: "neutral", icon: Loader2, label: "Queued" },
  running: { tone: "lamp", icon: Loader2, label: "Running" },
  succeeded: { tone: "keep", icon: CheckCircle2, label: "Done" },
  failed: { tone: "cut", icon: XCircle, label: "Failed" },
} as const;

export function JobPanel({ jobs, loading }: { jobs: Job[]; loading: boolean }) {
  return (
    <Card>
      <CardHeader
        title="Ingestion runs"
        description="Live progress for this server session. History resets when the server restarts."
      />
      <CardBody className="pt-0">
        {jobs.length === 0 ? (
          <EmptyState
            icon={FolderOpen}
            title={loading ? "Loading runs" : "No ingestion runs yet"}
            description={
              loading
                ? "Checking what this server has indexed."
                : "Start one above and its log will stream here line by line."
            }
            className="py-10"
          />
        ) : (
          <ul className="space-y-2">
            <AnimatePresence initial={false}>
              {jobs.map((job) => (
                <motion.li
                  key={job.id}
                  layout
                  initial={{ opacity: 0, y: -6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.18 }}
                >
                  <JobRow job={job} />
                </motion.li>
              ))}
            </AnimatePresence>
          </ul>
        )}
      </CardBody>
    </Card>
  );
}

function JobRow({ job }: { job: Job }) {
  const log = useRef<HTMLDivElement>(null);
  const status = STATUS[job.status];
  const SourceIcon = SOURCE_ICON[job.source as keyof typeof SOURCE_ICON] ?? FolderOpen;
  const StatusIcon = status.icon;
  const active = job.status === "running" || job.status === "queued";

  // Keep the newest line visible while a run is live, but stop hijacking the
  // scroll once it has finished and the user may be reading the middle.
  useEffect(() => {
    if (active && log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [job.logs.length, active]);

  return (
    <div className="rounded-control border border-rule bg-panel">
      <div className="flex items-start gap-2.5 p-3">
        <span
          aria-hidden
          className={cn(
            "mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-control border transition-colors",
            active ? "border-lamp-line bg-lamp-soft text-lamp" : "border-rule bg-panel text-moon-3",
          )}
        >
          <SourceIcon className="size-3.5" />
        </span>

        <div className="min-w-0 flex-1">
          <p className="truncate font-mono text-xs text-moon" title={job.target}>
            {job.target}
          </p>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[0.6875rem] text-moon-3">
            <span>→ {job.collection}</span>
            <span className="tabular-nums">{formatTime(job.created_at)}</span>
            {job.summary?.chunks !== undefined && (
              <span>
                {formatCount(job.summary.chunks)} chunks from {formatCount(job.summary.files ?? 0)}{" "}
                files
              </span>
            )}
          </p>
        </div>

        <Badge tone={status.tone} icon={StatusIcon} className={cn(active && "[&>svg]:animate-spin")}>
          {status.label}
        </Badge>
      </div>

      {/* A live sweep under the run while it works — indeterminate, because
          chunking has no honest progress bar. It just says "still moving". */}
      {active && (
        <div aria-hidden className="h-0.5 w-full overflow-hidden bg-panel-2">
          <div className="sweep h-full w-1/3 rounded-pill bg-lamp/60" />
        </div>
      )}

      {job.logs.length > 0 && (
        <div
          ref={log}
          // A log is a running commentary, not a result — announcing every line
          // would flood a screen reader, so it is deliberately not a live region.
          className="max-h-40 overflow-y-auto border-t border-rule bg-ink px-3 py-2 font-mono text-[0.6875rem] leading-relaxed text-moon-2"
        >
          {job.logs.map((line, index) => (
            <p key={index} className="whitespace-pre-wrap break-words">
              {line}
            </p>
          ))}
        </div>
      )}

      {job.error && (
        <p
          role="alert"
          className="border-t border-cut/30 bg-cut-soft px-3 py-2 text-[0.6875rem] leading-relaxed text-moon"
        >
          {job.error}
        </p>
      )}
    </div>
  );
}
