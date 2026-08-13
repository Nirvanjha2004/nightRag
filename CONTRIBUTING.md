# Contributing

Thanks for taking a look. This project is small enough that the fastest way in
is to read `app/` top to bottom — every module has a docstring explaining why it
exists, not just what it does.

## Getting set up

```bash
pip install -r requirements.txt
cp .env.example .env          # add your two API keys
cd web && npm install && cd ..

python run_server.py          # API + built UI on :8000
```

For UI work, run the two halves separately so both hot-reload:

```bash
python run_server.py          # terminal 1
cd web && npm run dev         # terminal 2 — http://localhost:5173, proxies /api
```

## Checks before opening a PR

```bash
python test_pipeline.py       # offline: no keys, no server, no network
python test_server.py         # offline: routes, SSE streaming, ingest validation
cd web && npm run typecheck && npm run build
```

Both run entirely against fakes — a hash-based embedder, an in-memory Qdrant and
a scripted generator — so they catch wiring breaks in seconds without spending
an API call. `test_pipeline.py` covers chunking, fusion, reranking and
corrective RAG; `test_server.py` covers everything above the pipeline, including
the order events arrive in on the stream.

## How the pieces fit

```
app/chunking.py        tree-sitter → one chunk per function/class/method
app/embedder.py        Jina embeddings, batched
app/vector_db.py       Qdrant wrapper, thread-safe
app/bm25_retriever.py  lexical search over the same chunks
app/hybrid_retriever.py  BM25 + dense, in parallel
app/fusion.py          reciprocal rank fusion
app/llm_reranker.py    LLM scores candidates 1–5
app/corrective_rag.py  grade → rewrite → re-retrieve → refine
app/rag_pipeline.py    prepare() then generate
app/factory.py         wires all of the above from one config
app/trace.py           stage events the UI renders
server/                FastAPI: /api/ask (SSE), /api/ingest, /api/collections
web/                   React UI
```

Two rules the existing code follows, worth keeping:

1. **Every LLM-dependent stage degrades.** A reranker that cannot parse its
   response falls back to fused order; a corrective round that fails falls back
   to the original retrieval. Nothing in the pipeline may make retrieval *worse*
   than not running it.
2. **Retrieval components share one interface** — `retrieve(query, top_k)`
   returning `list[RetrievedChunk]`. That is why the reranker, the hybrid
   retriever and the plain retriever are interchangeable.

## Changing the API contract

`server/schemas.py` and `web/src/lib/api.ts` mirror each other by hand. Change
both in the same commit.

## Evaluation

Benchmark changes to retrieval quality rather than eyeballing them:

```bash
pip install -r requirements-eval.txt
python run_evals.py           # runs benchmarks/evals.jsonl → eval_results.jsonl
python run_ragas.py           # scores it (needs a local Ollama judge)
```

`journey/` records what each previous run measured and what changed because of
it; `issues/` records the failures found along the way. A PR that moves the
numbers should add a `journey/` entry.
