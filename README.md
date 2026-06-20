# PDF RAG with clickable page citations

A Retrieval-Augmented Generation system over a **scanned technical PDF** (a ~670-page
Cessna 172 parts catalog). It answers questions grounded *only* in the document, and
every citation is a **clickable `[página N]` that jumps a PDF viewer to the exact page**.
It ships with a FastAPI backend and a React web GUI.

It started as a minimal text RAG (Postgres + PGVector) and grew, stage by stage, into the
full pipeline below. It's built to be read: every stage is small and explicit, and where a
real system would reach for a heavier component this one picks the simplest thing that's
still correct and notes the trade-off.

## What it does

- **OCR** every page of a scanned PDF (the embedded text layer is partial garbage) and
  index it, **carrying the page number through every stage**.
- **Hybrid retrieval**: semantic (vector) + lexical (full-text) search fused with
  Reciprocal Rank Fusion — so a fact buried in a dense table is found by meaning *or* by
  exact token (part numbers, codes), and you can search by part number directly.
- **Aggregation questions** ("how many ribs?", "list all adhesives", "most common fastener?")
  via a structured parts table + guarded text-to-SQL, routed by intent — the part of the
  catalog that top-k retrieval can't answer on its own.
- **Grounded answers** that cite `[página N]`, refusing to guess when the corpus has no
  relevant context (anti-hallucination relevance gate).
- **Clickable citations**: the frontend parses `[página N]` and jumps the PDF viewer to
  that page — the model answers from text, the human verifies on the image.

## Architecture

Two phases. Ingestion runs offline, once per document; the query path runs per question.

**Ingestion (offline)**

```
data/<scan>.pdf
   │  render each page to an image (PyMuPDF, 200 DPI) → OCR (Tesseract)
   ▼
[{page_number, text}]  ──cache──▶  data/<name>_ocr.json
   │  chunk PER PAGE (one chunk never spans two pages → exact-page citations)
   ▼
text chunks ──embed (batched ≤2048)──▶ OpenAI text-embedding-3-small (1536-d)
   ▼
PostgreSQL + PGVector
  documents(content, source, chunk_index, page_number, content_hash, embedding, tsv)
  + HNSW index on embedding (cosine)  + GIN index on tsv (full-text)
```

**Query (online)**

```
user question
   │
   ├─ vector arm:  embed (same model) → cosine k-NN (HNSW, <=>)      → 20 candidates
   ├─ lexical arm: Postgres full-text (websearch_to_tsquery, GIN)    → 20 candidates
   ▼
Reciprocal Rank Fusion (RRF)  → ~20 candidates
   │
   ├─ relevance gate (min cosine distance > T → refuse, no LLM call)
   ▼
LLM reranker (listwise) → reorder → top-k (10) chunks
   ▼
grounded prompt (context block, each chunk tagged with its page)
   ▼
OpenAI gpt-4o-mini (temperature 0) → answer citing [página N]
   ▼
FastAPI /ask  →  React frontend renders [página N] as buttons → click jumps the viewer
```

## Quickstart

You need Docker and an OpenAI API key. Copy the env file and set your key:

```bash
cp .env.example .env
# edit .env and set OPENAI_API_KEY
```

### 1. OCR the PDF (once)

Put a scanned PDF in `data/` and extract its text to a JSON cache (Tesseract runs inside
the container — nothing to install locally):

```bash
make docker-ocr                       # previews the first pages to sanity-check OCR
# full run + persist the cache (host file), then ingest it:
docker compose run --rm -T --entrypoint python app - < /dev/null  # see Makefile / docs
```

### 2. Backend + Q&A

```bash
make docker-api      # builds the image, starts Postgres + the API on :8000
# health: curl localhost:8000/health   ·   docs: http://localhost:8000/docs
```

`POST /ask {"query": "..."}` returns the answer, the cited pages, the source chunks and
the min distance. `GET /pdf` serves the PDF for the viewer.

### 3. Frontend

```bash
cd frontend && npm install && npm run dev     # http://localhost:5173
```

Ask a question, then click a `[página N]` citation — the viewer jumps to that page.

### Local development & tests

```bash
make install-dev    # uv venv + dependencies + pytest
make test           # the suite is fully mocked (no DB, no API key, no network)
```

`make help` lists every target.

## How it works

**OCR, not the embedded text.** The scan ships with a partial, corrupt OCR layer, so we
ignore `get_text()` and instead render each page to an image and run Tesseract. Slower, but
the coverage and quality are far better and predictable. The result is cached to JSON so OCR
(the expensive step) runs at most once.

**The page number is the through-line.** `page_number` travels extraction → chunk → retrieval
→ citation → click → viewer jump. Chunking is **per page** (one chunk never spans two pages),
so a `[página N]` citation always points at a single, exact page.

**Hybrid retrieval.** The vector arm understands meaning; the lexical arm (Postgres full-text
over a generated `tsvector` column, GIN-indexed) catches literal tokens — part numbers, codes,
distinctive words — that a dense embedding buries inside a big chunk. The two ranked lists are
fused with **Reciprocal Rank Fusion** (`score = Σ 1/(k+rank)`), which needs no score
normalization because it uses ranks, not the (incomparable) cosine-distance and `ts_rank`
scales.

**Reranking.** Hybrid retrieval has good recall but coarse ordering (the right chunk can
land deep). A listwise LLM reranker re-scores the ~20 fused candidates jointly with the
question and narrows them to the top-k for the prompt. It reuses the chat model (no heavy
cross-encoder dependency), fails open (any error keeps the hybrid order), and runs only
after the relevance gate so out-of-domain queries cost no rerank call. Measured on the
eval gold set: recall@5 0.73 → 0.91 and MRR@10 0.39 → 0.69 over hybrid alone.

**Aggregation vs. lookup.** Retrieve-then-read can't answer "how many" / "list all" / "most
common" — it only sees the top-k chunks, not the whole catalog. An intent router sends those
to a structured `parts` table (parsed from the OCR) and answers with guarded text-to-SQL
(read-only, single SELECT, `parts`-only, LIMIT), citing pages. If the SQL returns no rows
(e.g. the column-split materials section), it falls back to the semantic path. Point lookups
go straight to retrieval.

**Refusing instead of guessing.** A retriever always returns *something*. If the closest chunk
by cosine distance is farther than a threshold, the system skips the LLM call and answers an
honest "not enough information". The gate stays vector-based even under hybrid search, so a
stray keyword match can't smuggle an out-of-domain question past it.

**Grounding & citations.** Retrieved chunks go into a `<context>` block, each tagged with its
page. The system prompt forces answers from context only and citations in the exact
`[página N]` format — chosen so the frontend can parse it with a simple regex and turn each
citation into a button.

## Design decisions

**OCR over the embedded text layer.** Concretely: on this scan, `page.get_text()` returns
strings like `"illustrated parts dialog"` / `"C % S M ~ Z"`. Re-OCR from the rendered image
is the only reliable source.

**PostgreSQL + PGVector, not a dedicated vector DB.** One system holds vectors, text, metadata
**and** the full-text index — vector search, keyword search and `WHERE` filters in the same SQL,
no extra moving parts. The right call at this scale, and exactly what makes hybrid search cheap
to add.

**Hybrid search + RRF.** Pure vector retrieval missed facts buried in dense, noisy OCR chunks.
RRF fuses the semantic and lexical arms without tuning weights. Two subtleties the catalog
forced: OCR glues words (`HANGER~HEADLINER`) so the `tsvector` expression strips `~ = |` before
tokenizing; and a 500-char window can split a term from its header, so the lexical arm uses OR
semantics and lets ranking + the vector arm restore precision.

**`content_hash = sha256(source + page_number + content)`.** Including the page keeps repeated
boilerplate (headers/footers) on different pages as distinct, citable rows, while keeping
ingestion idempotent (`ON CONFLICT DO NOTHING`). Inserts are batched (`execute_values`); the
new-row count uses `RETURNING` (cur.rowcount under-reports a paginated insert). Embeddings are
batched ≤2048 inputs/request (the OpenAI limit).

**HNSW + cosine; temperature 0; `top_k = 10`.** Approximate k-NN with good recall; deterministic,
testable answers; and a deeper context window (raised from 5) so hybrid's rescued hits actually
reach the prompt on dense tables.

**Config in one place.** `src/config.py` is the only module that reads the environment; its DB
defaults match `docker-compose.yml`, so the app connects out of the box.

## Project layout

```
src/
  config.py     environment configuration (single source of truth)
  db.py         connection + schema (table, HNSW + GIN indexes, unique constraint)
  pdf_loader.py PDF → per-page OCR text (PyMuPDF + Tesseract), JSON cache
  embed.py      text → embedding vectors (OpenAI), batched ≤2048
  ingest.py     chunk-per-page → embed → store (idempotent, batched)
  parts.py      structured parts extracted from the OCR (for aggregation queries)
  aggregate.py  intent router + guarded text-to-SQL over the parts table
  retrieve.py   vector + full-text arms, Reciprocal Rank Fusion, hybrid search
  rerank.py     LLM reranker (listwise) over the hybrid candidates
  rag.py        prompt building, relevance gate, grounded generation with [página N]
  api.py        FastAPI: /health, /ask, /pdf (CORS for local dev)
  main.py       interactive CLI
frontend/       React + Vite + TypeScript: PDF viewer + Q&A panel, clickable citations
eval/           retrieval evaluation (gold set + recall@k / MRR harness, `make eval`)
tests/          unit tests, fully mocked (OpenAI + DB)
docker/         container entrypoint (seeds schema + data on boot)
data/           the source PDF (gitignored) + OCR cache (gitignored)
```

## Tests

Fully mocked — no database, no API calls — so it's fast and free:

```bash
make test                       # backend (pytest)
npm --prefix frontend test      # frontend (vitest)
```

The backend suite covers chunking, the content hash, embedding batching, the relevance gate
(incl. the boundary case), retrieval result shape and **Reciprocal Rank Fusion**. The frontend
suite covers the `[página N]` citation parser. GitHub Actions runs the backend on every push
(`.github/workflows/ci.yml`).

## Notes

Developed in an iCloud Drive folder, which is unreliable to bind-mount into Docker, so the
image copies the source (and the PDF) in at build time rather than mounting it. Change code,
then rebuild. Postgres data lives in a Docker-managed named volume, never on the synced path;
`make clean` drops it.

## What's next

The honest list, roughly in order of impact:

- **A stronger reranker** — the current reranker reuses the chat LLM (listwise); a dedicated
  cross-encoder or a rerank API would be faster and cheaper per query in production.
- **Structure-aware chunking** — split on rows/sections instead of a fixed character window,
  so a part row isn't cut from its header.
- **Evaluation** — measure retrieval (recall@k, MRR) and faithfulness instead of judging by eye.
- **Diagram understanding** — the exploded-view pages are images; OCR only gets the caption, so
  the callout-number ↔ part-number mapping is lost. A vision model would recover it.
- **Streaming** — stream tokens for lower perceived latency.
```
