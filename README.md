# Mini-RAG

A small, educational, end-to-end Retrieval-Augmented Generation (RAG) pipeline in
Python. It ingests plain-text documents, stores their vector embeddings in
PostgreSQL via PGVector, and answers questions by retrieving the most relevant
chunks and asking an LLM to respond **only** from that retrieved context, with
inline citations. The goal is clarity over features: every stage is small enough
to read and understand.

## Architecture

The system has two distinct phases.

**1. Ingestion (offline, run once per document set):**

```
data/sample_docs.txt
      │  read + split into overlapping chunks
      ▼
   text chunks  ──embed──▶  OpenAI text-embedding-3-small (1536-d vectors)
      │
      ▼
PostgreSQL + PGVector
  documents(content, source, chunk_index, embedding vector(1536))
  + HNSW index on embedding (cosine)
```

**2. Query (online, per question):**

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

## Tech Stack

- **Python 3.10+** — pipeline logic.
- **PostgreSQL 16 + PGVector** — vector storage and similarity search (runs in Docker).
- **OpenAI API** — embeddings (`text-embedding-3-small`) and generation (`gpt-4o-mini`).
- **psycopg2** — PostgreSQL driver.
- **Docker / Docker Compose** — reproducible database.

## How it works

- **Chunking.** Documents are split into smaller, overlapping text chunks. Chunks
  keep retrieval focused (you embed and return a paragraph, not a whole file), and
  the overlap prevents losing meaning at chunk boundaries.
- **Embeddings.** Each chunk is converted into a 1536-dimensional vector that
  captures its semantic meaning. The query is embedded with the **same** model so
  the two live in the same vector space.
- **Vector storage (PGVector).** Vectors are stored in a `vector(1536)` column
  alongside the original text and metadata (`source`, `chunk_index`), so retrieval
  and the data it points back to live in one place.
- **Similarity search (cosine distance).** At query time we find the nearest chunks
  using cosine distance via PGVector's `<=>` operator, accelerated by an HNSW index.
  Distance ranges from 0 (identical direction) to 2 (opposite).
- **Grounded generation with citations.** Retrieved chunks are injected into the
  prompt inside a `<context>` block, numbered `[1]..[k]`. The system prompt forces
  the model to answer only from that context and cite the chunks it used.
- **Relevance threshold.** If the closest chunk is farther than a distance
  threshold, we assume nothing relevant was found and refuse to answer instead of
  letting the model hallucinate — and we surface the best distance for debugging.

## Setup & Run

**1. Start PostgreSQL + PGVector (Docker):**

```bash
docker compose up -d
docker compose ps          # confirm the postgres service is running
```

**2. Create a virtual environment and install dependencies:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**3. Configure environment variables:**

```bash
cp .env.example .env
# edit .env and set OPENAI_API_KEY
```

**4. Ingest the sample documents:**

```bash
python -m src.ingest
```

**5. Run the interactive demo:**

```bash
python -m src.main
```

You'll be asked whether to (re)ingest, then you can ask questions in a loop. Type
`exit` or `quit` to leave.

## Design decisions

- **PostgreSQL + PGVector instead of a dedicated vector DB.** One system stores both
  the vectors and the source text/metadata, with real SQL, transactions, and no
  extra infrastructure. Perfect for learning and for small-to-medium workloads.
- **HNSW + cosine distance.** HNSW gives fast approximate nearest-neighbor search
  with good recall; cosine distance compares semantic *direction* rather than
  magnitude, which is the standard choice for text embeddings.
- **Chunking with overlap.** Smaller chunks make retrieval precise; the overlap
  keeps sentences that straddle a boundary from losing their context.
- **Temperature 0.** RAG answers should be deterministic and faithful to the
  retrieved context, not creative. Temperature 0 minimizes drift and invention.
- **Relevance threshold.** A retriever always returns *something*. The threshold
  turns "nearest" into "actually relevant," so off-topic questions get an honest
  "I don't have enough information" instead of a confident hallucination.

## What I'd improve for production

- **Semantic chunking** — split on meaning (sentence/section boundaries, headings)
  rather than fixed character windows.
- **Hybrid search** — combine vector similarity with keyword/full-text search
  (BM25) to catch exact terms, IDs, and rare words that embeddings miss.
- **Reranking** — re-score the top-k with a cross-encoder before sending the best
  few to the LLM, improving precision.
- **Evaluation metrics** — measure retrieval (recall@k, MRR) and generation
  (faithfulness, answer relevance) instead of eyeballing outputs.
- **Streaming responses** — stream tokens to the user for lower perceived latency.
- **Retries with backoff** — handle transient OpenAI/network errors gracefully.
- **Idempotent ingestion** — dedupe by content hash and support incremental
  re-ingestion so re-running doesn't create duplicate chunks.
```
