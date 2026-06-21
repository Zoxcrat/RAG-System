# SPEC — Mini-RAG

Technical specification of the system. Design document prior to implementation
(spec-driven): defines the objective, architecture, contracts, locked-in decisions and
acceptance criteria. The scope is **educational**, not production-grade.

---

## 1. Objective and scope

Build an end-to-end RAG (Retrieval-Augmented Generation) pipeline, minimal but
complete, that answers natural language questions **grounded exclusively** in a
provided document corpus, with citations to sources and without hallucinating when
there is no relevant information.

> **Note (2026-06).** This started as a plain-text RAG and grew into a PDF Q&A system
> with clickable page citations and a web GUI. The sections below are updated to the
> current system; the original base-RAG spec is preserved where still accurate.

**In scope:**
- **PDF ingestion via OCR**: render each page (PyMuPDF) → OCR (Tesseract) → per-page text
  cache; the embedded text layer is ignored (it is partial and corrupt).
- **Chunking per page** carrying `page_number` end to end (extraction → chunk → retrieval
  → citation → click → viewer jump). Idempotent, batched embeddings.
- Vector storage and similarity search in PostgreSQL + PGVector.
- **Hybrid retrieval**: vector (cosine k-NN) + lexical (Postgres full-text) fused with
  Reciprocal Rank Fusion, then an **LLM reranker** over the candidate pool.
- **Aggregation path**: a structured `parts` table parsed from the OCR + intent routing +
  guarded text-to-SQL, for count/list/most-common questions (with semantic fallback).
- **Evaluation harness** (recall@k, MRR) over a curated gold set (`make eval`).
- Grounded generation with an LLM, `[página N]` citations and an anti-hallucination
  relevance threshold.
- **FastAPI** backend (`/health`, `/ask`, `/pdf`) and a **React + Vite + TypeScript**
  frontend (PDF viewer + Q&A panel, clickable citations).
- Interactive demo CLI.

**Out of scope (roadmap, not implemented):** a dedicated cross-encoder / rerank-API
reranker (current reranker reuses the chat LLM), structure-aware chunking (rows/sections),
metadata filtering, faithfulness evaluation, streaming. Query expansion is implemented but
**off by default** (it hurt recall on the eval set); diagram/vision understanding exists only
as a proof of concept.

**Locked-in technical constraints:** Python 3.12, PostgreSQL 16 with PGVector and Tesseract
(in Docker), OpenAI API for embeddings and generation, FastAPI/uvicorn, `psycopg2`,
`python-dotenv`. Frontend: React 18 + Vite + TypeScript, react-pdf (PDF.js).

---

## 2. Architecture

The code is grouped into three pipeline packages plus shared modules and entrypoints.
Dependencies flow in one direction (no cycles):

```
src/
  config, db, embed     shared
  api, main             entrypoints
  ingestion/  pdf_loader, ingest, parts
  retrieval/  retrieve, rerank, expand
  answer/     rag, aggregate

api ──► answer/rag ──┬─► retrieval/retrieve ──► retrieval/expand, embed ──► (OpenAI)
 │                   ├─► retrieval/rerank ───────────────────────────────► (OpenAI)
 │                   └─► answer/aggregate ──► text-to-SQL over parts ─────► (OpenAI)
main ──► ingestion/ingest ──► ingestion/parts, embed, db
 │       ingestion/pdf_loader (PDF → OCR JSON) ──feeds──┘
 └──► db ──► (PostgreSQL + PGVector)

every module ──► config ──► (environment / .env)
```

| Package / module | Responsibility |
|---|---|
| `config` | Single source of truth for configuration; the only module that reads `os.getenv`. |
| `db` | Postgres connection and schema (`vector` extension, `documents` + `parts` tables, HNSW + GIN indexes, content-hash unique index). |
| `embed` | Text → vectors via OpenAI, batched (≤2048 inputs/request). |
| **ingestion/** `pdf_loader` | Scanned PDF → per-page OCR text (PyMuPDF + Tesseract), JSON cache. |
| **ingestion/** `ingest` | OCR pages → chunk per page → batch embeddings → idempotent INSERT into `documents`. |
| **ingestion/** `parts` | Parses the OCR into the structured `parts` table for aggregation. |
| **retrieval/** `retrieve` | Hybrid search: vector + full-text arms fused with RRF (with optional multi-query). |
| **retrieval/** `rerank` | Listwise LLM reranker over the candidates (fail-open). |
| **retrieval/** `expand` | Query expansion (multi-query); off by default. |
| **answer/** `rag` | Query orchestration: route → retrieve → gate → rerank → grounded prompt → LLM → response. |
| **answer/** `aggregate` | Intent router + guarded text-to-SQL over `parts`, with semantic fallback. |
| `api` | FastAPI: `/health`, `/ask`, `/pdf` (CORS for dev). |
| `main` | Interactive CLI. |

**Data model** (`documents`):

| Column | Type | Notes |
|---|---|---|
| `id` | `SERIAL PRIMARY KEY` | |
| `content` | `TEXT NOT NULL` | original text chunk |
| `source` | `TEXT` | name of the source document |
| `chunk_index` | `INTEGER` | position of the chunk within the document |
| `page_number` | `INTEGER` | source page (1-based); `NULL` for plain text. The citation through-line. |
| `content_hash` | `TEXT` | SHA-256 of `source + page_number + content`; unique, used for idempotent ingestion |
| `embedding` | `vector(1536)` | embedding of the chunk |
| `tsv` | `tsvector` | full-text vector, **generated** from `content` (OCR noise `~ = \|` stripped first); the lexical arm |
| `created_at` | `TIMESTAMP DEFAULT NOW()` | |

Indexes: **HNSW** over `embedding` (`vector_cosine_ops`); **GIN** over `tsv`; **UNIQUE** over
`content_hash`. All schema/index creation is idempotent (`IF NOT EXISTS`), and new columns are
added to pre-existing tables with `ADD COLUMN IF NOT EXISTS`.

---

## 3. Key interfaces / contracts

### `db`
```python
get_connection() -> connection
# psycopg2 connection. Reads DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD from
# src.config, whose defaults match docker-compose.

init_schema(conn) -> None
# Idempotent: CREATE EXTENSION IF NOT EXISTS vector; creates documents table,
# HNSW index, and the content_hash UNIQUE index (all IF NOT EXISTS). Adds the
# content_hash column to pre-existing tables (ADD COLUMN IF NOT EXISTS). Commits.

reset_db(conn) -> None
# DROP TABLE documents and recreates the schema. Destructive (deletes data).

EMBEDDING_DIM = 1536  # from src.config
```

### `embed`
```python
embed_text(text: str) -> list[float]
# Returns a vector of dimension EMBEDDING_DIM.

embed_texts(texts: list[str]) -> list[list[float]]
# Batch. Splits into batches of EMBED_BATCH_SIZE (1000) to stay under OpenAI's
# 2048-inputs-per-request cap; preserves global input order. [] -> [].

EMBEDDING_MODEL = "text-embedding-3-small"
```

### `pdf_loader`
```python
extract_pages_from_pdf(pdf_path, dpi=200, max_pages=None, lang="eng") -> list[ExtractedPage]
# Render each page (PyMuPDF, zoom = dpi/72) and OCR it (Tesseract). Per-page error
# isolation (a failed page -> text=""), fail-fast if Tesseract is missing.
# ExtractedPage = {"page_number": int (1-based), "text": str}.
save_extracted_text(pages, path) / load_extracted_text(path)   # JSON cache (OCR runs once)
```

### `ingest`
```python
chunk_text(text, chunk_size=500, overlap=100) -> list[str]
# Sliding window over characters with overlap. step = chunk_size - overlap. Empty -> [].

ingest_pages(conn, pages: list[dict], source: str) -> int
# OCR pages [{page_number, text}] → chunk PER PAGE (each chunk keeps its page_number,
# never spans two pages) → batch embed → idempotent INSERT. Returns NEW rows.

ingest_file(conn, path: str) -> int
# Plain-text file → chunks with page_number=NULL. Idempotent. Returns NEW rows.
# content_hash = sha256(source + page_number + content). New-row count via RETURNING.
```

### `retrieve`
```python
retrieve(conn, query, top_k=10) -> list[dict]            # vector-only arm (cosine k-NN, <=>)
_keyword_search(conn, query, limit) -> list[dict]        # lexical arm (full-text, OR semantics)
reciprocal_rank_fusion(ranked_lists, top_k, rrf_k=60) -> list[dict]   # pure: score = Σ 1/(k+rank)
retrieve_hybrid(conn, query, top_k=10, candidates=20) -> list[dict]   # used by rag.ask
# Each dict: {"id","content","source","chunk_index","page_number","distance": float|None}
# distance is None for keyword-only hits (the relevance gate stays vector-based).
```

### `rerank`
```python
rerank(query, chunks, top_k) -> list[dict]      # listwise LLM rerank, returns top_k
# Reorders chunks by joint (query, passage) relevance. Fails OPEN: any API/parse
# error keeps the input order. [] -> [].
_parse_ranking(text, n) -> list[int]            # pure: model reply -> full 0-based permutation
# Tolerant: drops invalid/duplicate indices, appends omitted ones (never loses a candidate).
RERANK_ENABLED = True; RERANK_CANDIDATES = 20; RERANK_MODEL = "gpt-4o-mini"
```

### `rag`
```python
build_prompt(query: str, chunks: list[dict]) -> tuple[str, str]
# Returns (system_prompt, user_prompt). Each chunk is wrapped in
# <chunk page="N" source="X"> inside a <context> block; the system prompt requires
# answers from context only and citations in the EXACT format [página N] (so the
# frontend can parse them). Ends with "Question: {query}".

generate_answer(query: str, chunks: list[dict]) -> str
# If there are no chunks or min cosine distance > RELEVANCE_THRESHOLD: returns a
# "not enough information" message + best distance, WITHOUT calling the LLM.
# (Keyword-only chunks with distance None are ignored by the gate.)
# Otherwise: calls the LLM and returns the response. Errors -> friendly message.

ask(conn, query: str, top_k: int = 10) -> dict
# Orchestrates: retrieve_hybrid (RERANK_CANDIDATES) -> relevance gate on the
# candidates -> rerank to top_k (if enabled and gate passed) -> generate_answer.
# Returns {"query", "answer",
#          "sources": [{"id","source","chunk_index","page_number","distance"}],
#          "pages": [int],            # unique sorted pages of the retrieved chunks
#          "min_distance": float | None}

LLM_MODEL = "gpt-4o-mini"; TEMPERATURE = 0; MAX_TOKENS = 800
DEFAULT_TOP_K = 10; RELEVANCE_THRESHOLD = 0.5
RETRIEVAL_CANDIDATES = 20; RRF_K = 60   # hybrid search
```

### `api` (FastAPI)
```python
GET  /health  -> {"status": "ok"}                      # liveness, no DB
POST /ask     {query: str, top_k?: int} -> {query, answer, sources[...page_number],
                                            pages, min_distance}   # Pydantic-validated
GET  /pdf     -> the PDF bytes (application/pdf, FileResponse)     # for the viewer
# CORS enabled (CORS_ORIGINS, default "*"). DB connection per request (get_db dependency).
```

### `main`
```python
run_demo() -> None
# Connects, init_schema, asks whether to re-ingest, enters interactive loop.
# "exit"/"quit", Ctrl+C and Ctrl+D exit cleanly; other errors do not crash.
# Closes the connection on exit.
```

---

## 4. Design decisions locked in upfront

| Decision | Value | Reason |
|---|---|---|
| Embedding model | `text-embedding-3-small` | Good cost/latency for the scope; sufficient to demonstrate the pipeline. |
| Vector dimension | `1536` | Dimension of the chosen model. It is part of the schema: changing it requires migrating the column and re-embedding everything. |
| Index | HNSW | Approximate k-NN, fast and with good recall; acceptable trade-off (more memory and slower inserts) for a read-heavy system. |
| Distance metric | Cosine (`vector_cosine_ops`, `<=>`) | Standard for text embeddings; compares direction, not magnitude. Range 0 (identical) to 2 (opposite). |
| Text source | OCR (PyMuPDF + Tesseract), **not** `get_text()` | The scan's embedded text layer is partial/corrupt; re-OCR from the rendered image is the only reliable source. DPI 200, cached to JSON. |
| Chunking | Character window, `size=500`, `overlap=100`, **per page** | Small chunks → precise retrieval; chunk-per-page → every chunk has one exact `page_number`, so a `[página N]` citation is unambiguous. |
| Citation format | exact `[página N]` | Stable, regex-parseable on the frontend → turns each citation into a button that jumps the viewer. |
| Retrieval | **Hybrid** (vector + full-text) fused with **RRF** (`k=60`), `candidates=20`/arm | Vector misses facts buried in dense OCR chunks; the lexical arm catches literal tokens (part numbers). RRF needs no score normalization. |
| Reranking | **LLM listwise** over 20 candidates (reuse `gpt-4o-mini`), fail-open | Hybrid recall is good but ordering coarse. A cross-encoder-style rerank fixes order (MRR@10 0.39→0.69); reuse the chat model to avoid a torch dependency. Prod would use a dedicated cross-encoder / rerank API. |
| Generation | `temperature=0` | Deterministic responses faithful to the context, not creative. Auditable and testable. |
| `max_tokens` | `800` | Cap on response length/cost. |
| `top_k` | `10` (was 5) | Deeper context so hybrid's rescued hits reach the prompt on dense tables; cost stays trivial with `gpt-4o-mini`. |
| Relevance threshold | `0.5` (over the minimum **cosine** distance) | If the closest chunk exceeds the threshold, the LLM is not called and the system responds honestly. Stays vector-based under hybrid search. |

---

## 5. Acceptance criteria

**`db`**
- `get_connection()` opens a connection using env vars with defaults; the port is cast to `int`.
- `init_schema(conn)` is idempotent: running it N times does not fail nor duplicate objects. It leaves the `vector` extension, the `documents` table with the specified columns (incl. `page_number` and the generated `tsv`), the HNSW index (`vector_cosine_ops`), the GIN index on `tsv`, and the `content_hash` UNIQUE index created.
- `reset_db(conn)` leaves the table empty and with the schema recreated.

**`embed`**
- `embed_text` returns a list of floats of length `EMBEDDING_DIM` (1536).
- `embed_texts` returns one list per input, **in the same order**, splitting into batches of ≤2048 inputs/request; with empty input returns `[]` and makes no API call.

**`ingest`**
- `chunk_text` produces chunks of at most `chunk_size`, with overlap of `overlap` between consecutive ones; empty text → `[]`; does not generate empty chunks.
- `ingest_pages` chunks each page independently so every chunk carries its `page_number` and none spans two pages; `chunk_index` runs across the whole document; empty pages contribute nothing.
- Insertion is batched and idempotent (`content_hash = sha256(source + page_number + content)`, `ON CONFLICT (content_hash) DO NOTHING`); the new-row count uses `RETURNING` (accurate across `execute_values`' internal pages). `ingest_file` is the same with `page_number = NULL`.

**`retrieve`**
- `retrieve` (vector arm) returns at most `top_k` results **ordered by ascending cosine distance**; each includes `id`, `content`, `source`, `chunk_index`, `page_number` and `distance` (float). Empty table → `[]`.
- `reciprocal_rank_fusion` scores a doc as `Σ 1/(rrf_k + rank)` over the input lists, keeps the variant carrying a distance, and returns the top_k by score. `retrieve_hybrid` fuses the vector and keyword arms; keyword-only hits carry `distance = None`.

**`rerank`**
- `_parse_ranking(text, n)` returns a full permutation of `range(n)`: valid 1-based indices first (no duplicates), omitted ones appended in order; junk input → `range(n)`.
- `rerank` returns at most `top_k` chunks reordered by the model; on any API/parse error it returns the input order (fail-open); empty input → `[]` with no API call.

**`rag`**
- `build_prompt` tags each chunk with its `page` inside `<context>`; the system prompt instructs to answer only from context, acknowledge missing info, cite in the exact `[página N]` format, and never invent pages or citations.
- `generate_answer` **does not call the LLM** if there are no chunks or if the minimum cosine distance (ignoring `None`) `> RELEVANCE_THRESHOLD`, reporting the best distance. An API failure returns a friendly message, never an unhandled exception.
- `ask` returns a dict with `query`, `answer`, `sources` (each with `page_number` and `distance`), `pages` (unique sorted) and `min_distance`.

**`api`**
- `/health` returns `{"status":"ok"}` without touching the DB. `/ask` validates the body with Pydantic (empty `query` or `top_k<=0` → 422) and returns the `ask` payload. `/pdf` serves the PDF as `application/pdf`. Internal failures become a JSON 500, not a stack trace.

**`main`**
- Initializes the schema on startup and offers optional re-ingestion.
- The loop answers questions showing the response, cited sources and `min_distance`.
- `exit`/`quit`, Ctrl+C and Ctrl+D terminate cleanly; any other error is reported without breaking the session. The connection is always closed on exit.
