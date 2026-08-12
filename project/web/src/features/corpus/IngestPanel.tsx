import { useRef, useState, type DragEvent } from "react";
import { FileArchive, FolderOpen, GitBranch, Upload } from "lucide-react";
import { api, ApiError, type Job } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Field, TextInput } from "@/components/ui/Field";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/lib/utils";

type SourceKind = "path" | "git" | "upload";

const TABS: { kind: SourceKind; label: string; icon: typeof FolderOpen }[] = [
  { kind: "path", label: "Folder", icon: FolderOpen },
  { kind: "git", label: "Git URL", icon: GitBranch },
  { kind: "upload", label: "Zip", icon: FileArchive },
];

const PLACEHOLDERS: Record<Exclude<SourceKind, "upload">, { label: string; hint: string; placeholder: string }> = {
  path: {
    label: "Folder on the server",
    hint: "An absolute path on the machine running NightRag. Every .py file under it is chunked; virtualenvs, caches and node_modules are skipped.",
    placeholder: "C:\\code\\my-project",
  },
  git: {
    label: "Repository URL",
    hint: "Cloned shallowly (--depth 1) into a temporary directory, then discarded once the chunks are stored.",
    placeholder: "https://github.com/user/repo.git",
  },
};

interface IngestPanelProps {
  defaultCollection: string;
  /** Called with the newly created job so the caller can start tracking it. */
  onStarted: (job: Job) => void;
}

export function IngestPanel({ defaultCollection, onStarted }: IngestPanelProps) {
  const toast = useToast();
  const [kind, setKind] = useState<SourceKind>("path");
  const [value, setValue] = useState("");
  const [collection, setCollection] = useState(defaultCollection);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const ready = kind === "upload" ? file !== null : value.trim().length > 0;

  const submit = async () => {
    if (!ready || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const target = (collection || defaultCollection).trim();
      const job =
        kind === "upload"
          ? await api.ingestUpload(file!, target)
          : await api.ingest(kind, value.trim(), target);
      onStarted(job);
      toast.info(`Ingestion started into "${job.collection}".`);
      setValue("");
      setFile(null);
    } catch (caught) {
      const message =
        caught instanceof ApiError ? caught.message : "The ingestion could not be started.";
      setError(message);
      toast.error(message);
    } finally {
      setSubmitting(false);
    }
  };

  const acceptFile = (dropped: File | undefined) => {
    if (!dropped) return;
    if (!dropped.name.toLowerCase().endsWith(".zip")) {
      setError("Only .zip archives can be uploaded.");
      return;
    }
    setError(null);
    setFile(dropped);
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    acceptFile(event.dataTransfer.files[0]);
  };

  return (
    <Card>
      <CardHeader
        title="Add a codebase"
        description="Chunk, embed and index every Python file so it can be searched."
      />
      <CardBody className="space-y-4">
        <div role="tablist" aria-label="Source type" className="flex gap-1 rounded-control bg-surface-hover p-1">
          {TABS.map(({ kind: tabKind, label, icon: Icon }) => (
            <button
              key={tabKind}
              type="button"
              role="tab"
              aria-selected={kind === tabKind}
              onClick={() => {
                setKind(tabKind);
                setError(null);
              }}
              className={cn(
                "flex flex-1 items-center justify-center gap-1.5 rounded-[0.375rem] px-3 py-1.5",
                "text-[0.8125rem] font-medium transition-colors",
                kind === tabKind
                  ? "bg-surface text-fg shadow-[0_1px_2px_rgba(0,0,0,0.2)]"
                  : "text-fg-muted hover:text-fg",
              )}
            >
              <Icon aria-hidden className="size-3.5" />
              {label}
            </button>
          ))}
        </div>

        {kind === "upload" ? (
          <div>
            <p className="mb-1.5 text-[0.8125rem] font-medium text-fg">Zip archive</p>
            <div
              onDragOver={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              className={cn(
                "flex flex-col items-center rounded-control border border-dashed px-4 py-8 text-center transition-colors",
                dragging ? "border-accent bg-accent-soft" : "border-line-strong bg-surface-raised",
              )}
            >
              <Upload aria-hidden className="mb-2.5 size-5 text-fg-subtle" />
              {file ? (
                <p className="text-[0.8125rem] text-fg">
                  <span className="font-mono">{file.name}</span>{" "}
                  <span className="text-fg-subtle">({Math.round(file.size / 1024)} KB)</span>
                </p>
              ) : (
                <p className="text-[0.8125rem] text-fg-muted">Drop a .zip here, or</p>
              )}
              <Button
                size="sm"
                variant="secondary"
                className="mt-2.5"
                onClick={() => fileInput.current?.click()}
              >
                {file ? "Choose a different file" : "Browse files"}
              </Button>
              <input
                ref={fileInput}
                type="file"
                accept=".zip,application/zip"
                className="sr-only"
                onChange={(event) => acceptFile(event.target.files?.[0])}
              />
            </div>
            <p className="mt-1.5 text-xs leading-relaxed text-fg-muted">
              The archive is extracted to a temporary directory and deleted after indexing.
            </p>
          </div>
        ) : (
          <Field label={PLACEHOLDERS[kind].label} hint={PLACEHOLDERS[kind].hint}>
            {({ id, describedBy }) => (
              <TextInput
                id={id}
                aria-describedby={describedBy}
                value={value}
                spellCheck={false}
                placeholder={PLACEHOLDERS[kind].placeholder}
                onChange={(event) => setValue(event.target.value)}
                onKeyDown={(event) => event.key === "Enter" && submit()}
                className="font-mono text-[0.8125rem]"
              />
            )}
          </Field>
        )}

        <Field
          label="Collection"
          hint="Ingesting into an existing collection adds to it; chunks with the same identity are replaced."
        >
          {({ id, describedBy }) => (
            <TextInput
              id={id}
              aria-describedby={describedBy}
              value={collection}
              spellCheck={false}
              placeholder={defaultCollection}
              onChange={(event) => setCollection(event.target.value)}
              className="font-mono text-[0.8125rem]"
            />
          )}
        </Field>

        {error && (
          <p
            role="alert"
            className="rounded-control border border-critical/30 bg-critical-soft px-3 py-2 text-xs leading-relaxed text-fg"
          >
            {error}
          </p>
        )}

        <Button variant="primary" onClick={submit} disabled={!ready} loading={submitting}>
          {submitting ? "Starting…" : "Start ingestion"}
        </Button>
      </CardBody>
    </Card>
  );
}
