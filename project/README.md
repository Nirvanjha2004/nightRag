# NightRag

Ask questions about a Python codebase and get answers grounded in the actual
code — with every retrieval decision on the record.

Most RAG demos hide the retrieval step and hope the answer looks right.
NightRag does the opposite: hybrid search, an LLM reranking pass and a
self-correcting retrieval round all report what they did, and the UI shows you
the trace next to the answer. When the pipeline decides your question was
badly phrased and rewrites it, you see the rewrite.

```
question ─► BM25 ─┐
                  ├─► RRF fusion ─► LLM rerank ─► grade ─┬─► answer
           dense ─┘                                      │
                                                         └─► rewrite ─► retry
```

---

## Quick start

You need Python 3.11+, Node 20+, and two free API keys:
[Jina](https://jina.ai/embeddings/) (embeddings) and
[Groq](https://console.groq.com/keys) (generation).

### With uv (recommended)

[uv](https://docs.astral.sh/uv/) creates the virtualenv and pins every
dependency in one step:

```bash
uv sync                          # create .venv and install dependencies
cp .env.example .env             # paste your two keys in

cd web && npm install && npm run build && cd ..
uv run python run_server.py
```

`uv run` executes inside the project's `.venv`, so every command below can be
run the same way — e.g. `uv run python main.py "…"` or, via the installed
console scripts, `uv run nightrag "…"` and `uv run nightrag-server`.

### With pip instead

```bash
pip install -r requirements.txt
cp .env.example .env             # paste your two keys in

cd web && npm install && npm run build && cd ..
python run_server.py
```

Either way, open <http://127.0.0.1:8000>, go to **Corpus**, point it at a
folder or a Git URL, and start asking once it finishes indexing.

### With Docker instead

```bash
cp .env.example .env          # paste your two keys in
docker compose up --build
```

---

## What it actually does

**Chunking that respects code structure.** `tree-sitter` parses each file and
emits one chunk per top-level function, class and method — never a fixed-size
window that cuts a function in half. A class with methods is split into a header
chunk (decorators, signature, docstring, class-level attributes) plus one chunk
per method, so "what does `Foo.bar` do" retrieves `Foo.bar` and not all 400
lines of `Foo`.

**Hybrid retrieval.** Dense vectors find semantically similar code; BM25 finds
the exact symbol you typed. Both run concurrently and merge with reciprocal
rank fusion, so a question containing a literal function name and a question
phrased in prose both work.

**LLM reranking.** RRF only knows about rank, so it can promote a lexically
rich but semantically wrong chunk. A wider candidate set is scored 1–5 for
relevance and the best survive.

**Corrective RAG.** Before generating, an LLM grades the retrieval
correct / ambiguous / incorrect. Ambiguous or incorrect retrievals trigger a
symbol-rich query rewrite and a second round; chunks graded irrelevant are
dropped from the prompt entirely.

Every one of those stages degrades safely. If the reranker's response cannot be
parsed, retrieval falls back to fused order. If the corrective round retrieves
something worse, the original set is used. A stage failing never makes the
answer worse than not running it.

---

## Three ways to use it

### Web UI

`python run_server.py` serves the API and the built UI on one port. Ask
questions, watch the pipeline run stage by stage, click any source chunk to read
the code it came from, and tune the pipeline live from **Settings**.

### CLI

```bash
uv run python -m app.ingestion /path/to/repo --local   # index a codebase
uv run python main.py "Where is the overdraft fee defined?"
uv run python main.py                                  # interactive REPL
```

The same commands work as installed scripts: `uv run nightrag-ingest`,
`uv run nightrag`. Flags: `--top-k`, `--rrf-k`, `--candidate-k`,
`--min-score`, `--model`, `--no-rerank`, `--no-crag`. Run
`uv run python main.py --help` for the full list.

### HTTP API

Interactive docs at `/docs`. The endpoints that matter:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Keys, collections, defaults |
| `POST` | `/api/ask` | One-shot answer with sources and trace |
| `POST` | `/api/ask/stream` | The same, streamed as Server-Sent Events |
| `POST` | `/api/ingest` | Index a server path or a Git URL |
| `POST` | `/api/ingest/upload` | Index an uploaded `.zip` |
| `GET` | `/api/ingest/jobs/{id}` | Follow an ingestion |
| `GET` | `/api/collections` | What is indexed |

```bash
curl -s localhost:8000/api/ask \
  -H 'content-type: application/json' \
  -d '{"question":"How are rate limits retried?","options":{"top_k":5}}'
```

---

## Configuration

Everything is read from `.env` (see `.env.example` for the annotated list).
Only the two API keys are required.

The pipeline knobs — chunk count, candidate width, RRF constant, reranker
on/off, minimum relevance, corrective RAG on/off, model — are all overridable
per request, and the **Settings** screen writes them into every question you
ask. Nothing there is stored on the server, so two people using the same
instance can run different configurations.

### Storage

By default NightRag uses an embedded Qdrant store in `qdrant_data/`. That
directory is locked by exactly one process, which means **the server and the CLI
cannot run at the same time** against it. For anything shared, run a Qdrant
server and set `NIGHTRAG_QDRANT_URL`.

### Deploying it where others can reach it

Two things to change before that:

- Set `NIGHTRAG_ALLOW_LOCAL_PATH=0`. The "Folder" ingestion source reads the
  filesystem of the machine running the server — fine on your laptop, not fine
  on a shared host.
- Put it behind your own authentication. NightRag has none, and both API keys
  are spendable by anyone who can reach `/api/ask`.

### Deploying to Render

The repo ships a `render.yaml` Blueprint and a multi-stage `Dockerfile` that
builds the web UI and runs the API in one container. To deploy:

1. Push this repo to GitHub.
2. Render dashboard → **New +** → **Blueprint** → pick the repo.
3. Paste `JINA_API_KEY` and `GROQ_API_KEY` in the **Environment** tab (the
   Blueprint leaves them blank on purpose).
4. Storage — pick one:
   - **Paid instance (Starter $7/mo)**: keep the Blueprint's persistent disk,
     mounted at `/data`. The index survives redeploys.
   - **Free plan**: remove the `disk:` block and set `NIGHTRAG_QDRANT_URL` to a
     hosted Qdrant (e.g. Qdrant Cloud free tier) plus `NIGHTRAG_QDRANT_API_KEY`.
     The embedded store cannot work on the free plan — its filesystem is wiped
     on every redeploy.
5. Deploy, then check **Logs** and open `https://<your-app>.onrender.com`.

Render injects `PORT` and the app listens on it automatically (settings fall
back from `NIGHTRAG_PORT` to `PORT`); the health check is `/api/health`. Keep
`NIGHTRAG_ALLOW_LOCAL_PATH=0` (the Dockerfile sets it) and know that the URL is
public — anyone with it can spend your API keys.

---

## Development

```bash
uv run python run_server.py  # terminal 1 — API on :8000
cd web && npm run dev        # terminal 2 — UI on :5173, proxies /api
```

Before committing:

```bash
uv run python test_pipeline.py                 # pipeline wiring — offline, no keys
uv run python test_server.py                   # HTTP + streaming — offline, no keys
cd web && npm run typecheck && npm run build
```

Both test files run against fakes: a hash-based embedder, an in-memory Qdrant
and a scripted generator. They catch wiring breaks in seconds without spending
an API call.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the module map and the two design
rules the code follows.

---

## Benchmarks

Retrieval quality is measured, not asserted:

```bash
uv sync --extra eval        # adds the RAGAS + judge dependencies
uv run python run_evals.py  # benchmarks/evals.jsonl → eval_results.jsonl
uv run python run_ragas.py  # RAGAS scores (needs a local Ollama judge)
```

(`pip install -r requirements-eval.txt` works too if you are not on uv.)

`journey/` records what each run measured and what changed as a result —
baseline, RAGAS setup, hybrid retrieval, the reranker. `issues/` records the
failures found on the way there, including the ones that shaped the current
design (a truncated judge, a reasoning model returning empty scores, a
rate-limit stall).

---

## Project layout

```
app/          the pipeline — chunking, retrieval, reranking, correction
server/       FastAPI: streaming ask, ingestion jobs, collections
web/          React UI (Vite, Tailwind, TypeScript)
benchmarks/   golden question set
journey/      what each evaluation run changed
issues/       failures found and how they were fixed
main.py       CLI
run_server.py API + UI server
```

## License

MIT — see [LICENSE](LICENSE).
