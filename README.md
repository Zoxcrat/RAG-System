# Mini-RAG

A small, end-to-end Retrieval-Augmented Generation pipeline in Python. It ingests
plain-text documents, stores their embeddings in PostgreSQL via PGVector, and answers
questions by retrieving the most relevant chunks and asking an LLM to respond *only*
from that retrieved context, with inline citations.

It's built to be read: every stage is small and explicit, so the whole retrieval →
grounding → generation loop fits in your head. Where a real system would reach for a
heavier component, this one picks the simplest thing that's still correct and notes the
trade-off.

## Architecture

Two phases. Ingestion runs offline, once per document set; the query path runs per
question.

**Ingestion**

```
data/sample_docs.txt
      │  read + split into overlapping chunks
      ▼
   text chunks  ──embed──▶  OpenAI text-embedding-3-small (1536-d vectors)
      │
      ▼
PostgreSQL + PGVector
  documents(content, source, chunk_index, content_hash, embedding vector(1536))
  + HNSW index on embedding (cosine)
```

**Query**

```
user question
      │  embed with the SAME model
      ▼
vector similarity search (cosine distance, HNSW)  ──▶  top-k chunks
      │
      ├─ relevance threshold check (min distance > T → refuse)
      ▼
build grounded prompt  (context block + numbered chunks)
      │
      ▼
OpenAI gpt-4o-mini (temperature 0)  ──▶  grounded answer with [n] citations
```

## Quickstart

You need Docker and an OpenAI API key. Copy the env file and set your key:

```bash
cp .env.example .env
# edit .env and set OPENAI_API_KEY
```

### Run everything in Docker

No local Python required. This builds the image, starts Postgres, waits for it to be
healthy, creates the schema, and ingests the sample docs:

```bash
make docker-up
make docker-ask     # interactive Q&A loop; type 'exit' to leave
```

### Run locally (Python via uv, Postgres in Docker)

Handy for development and running the tests:

```bash
make install-dev    # uv venv + dependencies + pytest
make ingest         # starts Postgres, embeds and indexes the sample docs
make ask            # interactive demo
make test           # run the test suite (mocked, no DB or API needed)
```

`make help` lists every target.

## How it works

**Chunking.** Documents are split into overlapping character windows (500 chars, 100
overlap). Small chunks keep retrieval focused — you embed and return a passage, not a
whole file — and the overlap stops a sentence that straddles a boundary from losing its
meaning.

**Embeddings.** Each chunk becomes a 1536-dimensional vector. The query is embedded
with the same model, so question and chunks live in the same space.

**Storage.** Vectors sit in a `vector(1536)` column next to the original text and its
metadata (`source`, `chunk_index`, `content_hash`), so a retrieved vector always points
back to the text it came from.

**Search.** Retrieval is k-nearest-neighbour by cosine distance using PGVector's `<=>`
operator, backed by an HNSW index. Cosine distance runs from 0 (identical direction) to
2 (opposite).

**Grounding.** Retrieved chunks go into the prompt inside a `<context>` block, numbered
`[1]..[k]`. The system prompt tells the model to answer only from that context, to cite
the chunks it uses, and to say so when the answer isn't there.

**Refusing instead of guessing.** A retriever always returns *something*. If the closest
chunk is farther than a distance threshold, the system skips the LLM call entirely and
returns an honest "not enough information" (along with the best distance, which is handy
for tuning). That keeps an off-topic question from producing a confident, made-up answer.

## Design decisions

**PostgreSQL + PGVector, not a dedicated vector DB.** One system holds the vectors and
the source text and metadata, with real SQL and transactions and no extra moving parts.
That's the right call for this scale, and it leaves room to combine vector search with
ordinary `WHERE` filters later.

**HNSW + cosine.** HNSW gives fast approximate nearest-neighbour search with good
recall, at the cost of more memory and slower inserts — a good trade for a read-heavy
retrieval workload. Cosine compares direction rather than magnitude, the usual choice
for text embeddings.

**Idempotent ingestion.** Each chunk is stored with a `content_hash` (SHA-256) under a
unique index, and inserts use `ON CONFLICT DO NOTHING`. Re-running ingestion on the same
document inserts nothing instead of piling up duplicates. Inserts are batched with
`execute_values` rather than looping row by row.

**Temperature 0.** Answers should be deterministic and faithful to the retrieved text,
not creative, which also makes the system easy to test.

**Config in one place.** `src/config.py` is the only module that reads the environment.
Its database defaults match `docker-compose.yml`, so the app connects out of the box
even before you write a `.env`. The OpenAI client is configured with retries and a
timeout so a transient error doesn't crash a request.

## Project layout

```
src/
  config.py     environment configuration (single source of truth)
  db.py         connection + schema (table, HNSW index, unique constraint)
  embed.py      text → embedding vectors (OpenAI)
  ingest.py     chunk → embed → store (idempotent, batched)
  retrieve.py   embed query → cosine k-NN search
  rag.py        prompt building, relevance gate, answer generation
  main.py       interactive CLI
tests/          unit tests (mocked OpenAI + DB)
docker/         container entrypoint (seeds schema + data on boot)
data/           sample corpus
```

## Tests

The suite is fully mocked — no database and no API calls — so it's fast and free to run:

```bash
make test
```

It covers the chunking math, the relevance-threshold gate (including the boundary case),
and the shape of the retrieval results. GitHub Actions runs it on every push and pull
request (`.github/workflows/ci.yml`).

## Notes

The project was developed in an iCloud Drive folder, which is unreliable to bind-mount
into Docker, so the image copies the source in at build time rather than mounting it.
Change code, then `make docker-up` rebuilds. The Postgres data lives in a Docker-managed
named volume, never on the synced path. Use `make clean` to drop that volume and start
from an empty database.

## What's next

The honest list of things a production version would need, roughly in order of impact:

- **Hybrid search** — combine vector similarity with keyword/full-text (BM25) so exact
  terms, IDs, and codes that embeddings gloss over still match.
- **Structure-aware chunking** — split on sections, headings, and tables instead of a
  fixed character window, so a chunk is a complete unit of meaning.
- **Reranking** — re-score the top-k with a cross-encoder before handing the best few to
  the LLM.
- **Evaluation** — measure retrieval (recall@k, MRR) and generation (faithfulness)
  rather than judging by eye.
- **Streaming** — stream tokens for lower perceived latency.
