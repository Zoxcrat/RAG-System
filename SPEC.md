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

**In scope:**
- Ingestion of plain text documents: chunking, embeddings and persistence.
- Vector storage and similarity search in PostgreSQL + PGVector.
- Top-K retrieval by cosine distance.
- Grounded generation with an LLM, citations and an anti-hallucination relevance threshold.
- Interactive demo CLI.

**Out of scope (roadmap, not implemented):** hybrid search (vector + keyword),
reranking, semantic chunking, metadata filtering, evaluation harness, streaming,
retries/backoff, idempotent ingestion, multi-file and multi-format ingestion.

**Locked-in technical constraints:** Python 3.10+, PostgreSQL 16 with PGVector (in
Docker), OpenAI API for embeddings and generation, `psycopg2`, `python-dotenv`.

---

## 2. Architecture

Six modules in `src/`, each with a single responsibility. Dependencies flow in a
single direction (no cycles):

```
main ──► rag ──► retrieve ──► embed ──► (OpenAI API)
  │       │          │
  │       └──────────┴────► db ──► (PostgreSQL + PGVector)
  └────► ingest ──► embed, db
```

| Module | Responsibility |
|---|---|
| `db` | PostgreSQL connection and schema management (`vector` extension, `documents` table, HNSW index). Does not know about embeddings or the LLM. |
| `embed` | Convert text into vectors via OpenAI. The only point that calls the embeddings endpoint. |
| `ingest` | Offline pipeline: read file → chunking with overlap → batch embeddings → INSERT into `documents`. |
| `retrieve` | Search pipeline: embed the query → k-NN by cosine distance in PGVector → return chunks with metadata and distance. |
| `rag` | Orchestrates the query phase: building the grounded prompt, relevance threshold, LLM call, assembling the response. |
| `main` | Interactive CLI: initializes the schema, offers re-ingestion, question/answer loop. Presentation layer. |

**Data model** (`documents`):

| Column | Type | Notes |
|---|---|---|
| `id` | `SERIAL PRIMARY KEY` | |
| `content` | `TEXT NOT NULL` | original text chunk |
| `source` | `TEXT` | name of the source document |
| `chunk_index` | `INTEGER` | position of the chunk within the document |
| `embedding` | `vector(1536)` | embedding of the chunk |
| `created_at` | `TIMESTAMP DEFAULT NOW()` | |

Index: HNSW over `embedding` using `vector_cosine_ops`.

---

## 3. Key interfaces / contracts

### `db`
```python
get_connection() -> connection
# psycopg2 connection. Config from env vars (DB_HOST, DB_PORT, DB_NAME,
# DB_USER, DB_PASSWORD) with defaults for local development.

init_schema(conn) -> None
# Idempotent: CREATE EXTENSION IF NOT EXISTS vector; creates documents table
# (IF NOT EXISTS) and HNSW index (IF NOT EXISTS). Commits.

reset_db(conn) -> None
# DROP TABLE documents and recreates the schema. Destructive (deletes data).

EMBEDDING_DIM = 1536
```

### `embed`
```python
embed_text(text: str) -> list[float]
# Returns a vector of dimension EMBEDDING_DIM.

embed_texts(texts: list[str]) -> list[list[float]]
# Batch. Preserves input order. [] -> [].

EMBEDDING_MODEL = "text-embedding-3-small"
```

### `ingest`
```python
chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]
# Sliding window over characters with overlap. step = chunk_size - overlap.
# Empty text -> [].

ingest_file(conn, path: str) -> int
# Reads the file, chunks it, embeds in batch and inserts each chunk with its
# source (basename) and chunk_index. Returns the number of chunks inserted.
```

### `retrieve`
```python
retrieve(conn, query: str, top_k: int = 5) -> list[dict]
# Embeds the query and performs k-NN by cosine distance (operator <=>),
# ORDER BY distance ASC LIMIT top_k.
# Each dict: {"id", "content", "source", "chunk_index", "distance": float}
```

### `rag`
```python
build_prompt(query: str, chunks: list[dict]) -> tuple[str, str]
# Returns (system_prompt, user_prompt). The user_prompt wraps each chunk in
# <chunk id="N" source="X" chunk_index="Y"> inside a <context> block,
# numbered 1..K, followed by "Question: {query}".

generate_answer(query: str, chunks: list[dict]) -> str
# If there are no chunks or min(distance) > RELEVANCE_THRESHOLD: returns a
# "not enough information" message + best distance, WITHOUT calling the LLM.
# Otherwise: calls the LLM and returns the response. Errors -> friendly message.

ask(conn, query: str, top_k: int = 5) -> dict
# Orchestrates retrieve + generate_answer.
# Returns {"query", "answer", "sources": [{"id","source","chunk_index","distance"}],
#           "min_distance": float | None}

LLM_MODEL = "gpt-4o-mini"; TEMPERATURE = 0; MAX_TOKENS = 800
DEFAULT_TOP_K = 5; RELEVANCE_THRESHOLD = 0.5
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
| Chunking | Character window, `size=500`, `overlap=100` | Small chunks → precise retrieval; overlap → no loss of context at the edges. Deliberate simplicity. |
| Generation | `temperature=0` | Deterministic responses faithful to the context, not creative. Auditable and testable. |
| `max_tokens` | `800` | Cap on response length/cost. |
| `top_k` | `5` | Enough context without diluting the prompt. |
| Relevance threshold | `0.5` (over the minimum distance) | If the closest chunk exceeds the threshold, the LLM is not called and the system responds honestly. Prevents hallucinations on out-of-domain questions. |

---

## 5. Acceptance criteria

**`db`**
- `get_connection()` opens a connection using env vars with defaults; the port is cast to `int`.
- `init_schema(conn)` is idempotent: running it N times does not fail nor duplicate objects. It leaves the `vector` extension, the `documents` table with the 6 specified columns, and the HNSW index with `vector_cosine_ops` created.
- `reset_db(conn)` leaves the table empty and with the schema recreated.

**`embed`**
- `embed_text` returns a list of floats of length `EMBEDDING_DIM` (1536).
- `embed_texts` returns one list per input, **in the same order**; with empty input returns `[]`.

**`ingest`**
- `chunk_text` produces chunks of at most `chunk_size`, with overlap of `overlap` between consecutive ones; empty text → `[]`; does not generate empty chunks.
- `ingest_file` persists one record per chunk with `content`, `source` (basename of the path) and consecutive `chunk_index` starting at 0, and its `embedding`. Returns the number of chunks inserted.

**`retrieve`**
- Returns at most `top_k` results, **ordered by ascending cosine distance** (most relevant first).
- Each result includes `id`, `content`, `source`, `chunk_index` and `distance` (float). With an empty table → `[]`.

**`rag`**
- `build_prompt` numbers the chunks 1..K and wraps them with their `source` and `chunk_index` inside `<context>`; the system prompt instructs to answer only with the context, to acknowledge missing info, to cite `[n]` and not to make things up.
- `generate_answer` **does not call the LLM** if there are no chunks or if `min(distance) > RELEVANCE_THRESHOLD`, and in that case reports the best distance. An API failure returns a friendly message, never an unhandled exception.
- `ask` returns a dict with `query`, `answer`, `sources` (with `distance` per source) and `min_distance`.

**`main`**
- Initializes the schema on startup and offers optional re-ingestion.
- The loop answers questions showing the response, cited sources and `min_distance`.
- `exit`/`quit`, Ctrl+C and Ctrl+D terminate cleanly; any other error is reported without breaking the session. The connection is always closed on exit.
