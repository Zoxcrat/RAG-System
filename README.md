# PDF RAG with clickable page citations

A question-answering system over a scanned technical PDF (a ~670-page Cessna 172 parts
catalog). It answers only from the document, and every citation is a clickable `[página N]`
that jumps a PDF viewer to that page. Backend in FastAPI, frontend in React.

It started as a small text RAG on Postgres + PGVector and grew into the pipeline below:
OCR, hybrid retrieval, reranking, an aggregation path for "how many / list all" questions,
and a web UI.

## What it does

- OCRs every page of the scan (the embedded text layer is unreliable) and indexes it,
  keeping the page number attached to every chunk.
- Hybrid retrieval: vector search plus Postgres full-text search, fused with Reciprocal
  Rank Fusion, then an LLM reranker. Finds a fact by meaning or by exact token (you can
  search by part number directly).
- Answers aggregation questions ("how many ribs?", "list all adhesives", "most common
  fastener?") with a structured parts table and text-to-SQL, picked by an intent router.
- Cites `[página N]` and refuses to answer when nothing relevant was retrieved.
- The frontend turns each `[página N]` into a button that jumps the viewer to that page,
  so the answer is verifiable against the source.

## Architecture

Two phases. Ingestion runs once per document; the query path runs per question.

**Ingestion**

```
data/<scan>.pdf
   |  render each page to an image (PyMuPDF, 200 DPI) -> OCR (Tesseract)
   v
[{page_number, text}]  --cache-->  data/<name>_ocr.json
   |  chunk per page (a chunk never spans two pages, so a citation is one exact page)
   v
text chunks --embed--> OpenAI text-embedding-3-small (1536-d)
   v
PostgreSQL + PGVector
  documents(content, source, chunk_index, page_number, content_hash, embedding, tsv)
  + HNSW index on embedding (cosine)  + GIN index on tsv (full-text)
  parts(part_number, description, page_number, figure)   # for aggregation queries
```

**Query**

```
question
   |
   |-- aggregation? --> text-to-SQL over the parts table --> answer + [página N]
   |                    (falls back to retrieval if the SQL returns nothing)
   v
   vector arm:  embed -> cosine k-NN (HNSW)          -> 20 candidates
   lexical arm: Postgres full-text (GIN)             -> 20 candidates
   v
Reciprocal Rank Fusion
   |
   |-- relevance gate (closest chunk too far -> refuse, no LLM call)
   v
LLM reranker -> top-k (10) chunks -> grounded prompt
   v
gpt-4o-mini (temperature 0) -> answer citing [página N]
   v
FastAPI /ask  ->  React frontend renders [página N] as buttons -> click jumps the viewer
```

## Running it

You need Docker and an OpenAI API key.

```bash
cp .env.example .env        # then set OPENAI_API_KEY
```

**1. OCR the PDF and ingest it (once).** Put the scan in `data/`. `make docker-ocr` previews
the first pages so you can check the OCR. For the full run, render every page to text, save
it to `data/<name>_ocr.json`, then ingest it (this builds both the chunk index and the parts
table):

```bash
docker compose run --rm app python -m src.ingest data/<name>_ocr.json
```

**2. Backend.**

```bash
make docker-api     # builds the image, starts Postgres and the API on :8000
curl localhost:8000/health
```

`POST /ask {"query": "..."}` returns the answer, the cited pages and the source chunks.
`GET /pdf` serves the PDF for the viewer.

**3. Frontend.**

```bash
cd frontend && npm install && npm run dev   # http://localhost:5173
```

For local development and tests: `make install-dev`, then `make test` (mocked, no DB or API
key needed). `make help` lists the targets.

## How it works

**OCR instead of the embedded text.** The scan's text layer is partial and noisy
(`page.get_text()` returns things like `"illustrated parts dialog"`), so each page is
rendered to an image and run through Tesseract. Slower but reliable, and the result is cached
to JSON so OCR runs once.

**Page number as the through-line.** `page_number` travels from extraction to chunk to
retrieval to the `[página N]` citation to the viewer jump. Chunking is per page, so a citation
always points at one exact page.

**Hybrid retrieval.** Vector search captures meaning; Postgres full-text (a generated
`tsvector` column with a GIN index) catches literal tokens like part numbers that an embedding
buries inside a large chunk. The two ranked lists are fused with Reciprocal Rank Fusion, which
combines them by rank so the incomparable cosine and `ts_rank` scores never need normalizing.

**Reranking.** Hybrid retrieval has good recall but rough ordering. A listwise LLM reranker
re-scores the fused candidates and keeps the top-k for the prompt. It reuses the chat model,
falls back to the hybrid order on any error, and only runs after the relevance gate. On the
eval set it moved recall@5 from 0.73 to 0.91 and MRR@10 from 0.39 to 0.69 over hybrid alone.

**Aggregation questions.** Retrieve-then-read can't count or list everything, since it only
sees the top-k chunks. An intent router sends those questions to a structured `parts` table
(parsed from the OCR) and answers with text-to-SQL. The generated query is checked before it
runs (single read-only SELECT against `parts`, with a LIMIT) and the SQL is returned so the
answer is auditable. If it finds nothing, the question falls back to the semantic path.

**Refusing instead of guessing.** A retriever always returns something. If the closest chunk
is farther than a distance threshold, the system skips the LLM and says it doesn't have enough
information. The gate stays vector-based, so a stray keyword match can't push an off-topic
question through.

## Design notes

- **Postgres + PGVector, not a separate vector DB.** One system holds the vectors, the text,
  the metadata and the full-text index, so vector search, keyword search and `WHERE` filters
  all live in the same SQL. It is also what makes hybrid search cheap to add.
- **`content_hash = sha256(source + page_number + content)`.** Including the page keeps
  repeated headers/footers on different pages as separate, citable rows, and ingestion stays
  idempotent (`ON CONFLICT DO NOTHING`). Inserts are batched, and embeddings are sent in
  batches of ≤2048 (the API limit).
- **HNSW + cosine, temperature 0, top_k 10.** Fast approximate search with good recall,
  deterministic answers, and enough context for the reranked hits to reach the prompt.
- **Config in one place.** `src/config.py` is the only module that reads the environment,
  and its defaults match `docker-compose.yml`.

## Project layout

```
src/
  config.py     configuration (the only module that reads the environment)
  db.py         connection + schema (HNSW + GIN indexes, parts table)
  embed.py      text -> embedding vectors (batched)
  pdf_loader.py PDF -> per-page OCR text, cached to JSON
  parts.py      structured parts parsed from the OCR (for aggregation)
  ingest.py     chunk per page -> embed -> store
  retrieve.py   vector + full-text arms and RRF fusion
  rerank.py     LLM reranker over the candidates
  expand.py     query expansion (off by default, see config)
  aggregate.py  intent router + text-to-SQL over the parts table
  rag.py        prompt, relevance gate, answer generation
  api.py        FastAPI: /health, /ask, /pdf
  main.py       CLI
frontend/       React + Vite + TypeScript: PDF viewer and Q&A panel
eval/           retrieval evaluation (gold set + recall@k / MRR)
tests/          unit tests, mocked (no DB or API)
```

## Tests and evaluation

```bash
make test                     # backend, mocked (no DB, no API key)
npm --prefix frontend test    # frontend
make eval                     # retrieval quality on a small gold set (needs the DB + key)
```

`make eval` compares vector, hybrid and hybrid+rerank on labelled questions (recall@k and
MRR). CI runs the backend tests on every push.

## Possible next steps

- A dedicated cross-encoder or rerank API instead of the LLM reranker (cheaper per query).
- Structure-aware chunking (split on table rows instead of a fixed window).
- Reading the diagrams: the exploded-view pages are images, so the callout numbers are lost.
  A vision model could recover them (there is a working proof of concept).
- Token streaming for lower perceived latency.
```
