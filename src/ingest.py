import hashlib
import os
from typing import Optional

from psycopg2.extras import execute_values

from src import config
from src.db import get_connection, init_schema
from src.embed import embed_texts

CHUNK_SIZE = config.CHUNK_SIZE
CHUNK_OVERLAP = config.CHUNK_OVERLAP
SAMPLE_DOCS_PATH = "data/sample_docs.txt"

# (content, source, chunk_index, page_number); page_number is None for plain text.
ChunkRecord = tuple[str, str, int, Optional[int]]


def chunk_text(
    text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP
) -> list[str]:
    text = text.strip()
    if not text:
        return []

    step = chunk_size - overlap
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        chunk = text[start : start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks


def _to_vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(str(x) for x in embedding) + "]"


def _content_hash(source: str, page_number: Optional[int], content: str) -> str:
    """Dedup key for a chunk.

    Includes source and page_number so identical boilerplate on different pages
    stays as distinct, citable rows. Stable across re-ingestion, so ON CONFLICT
    DO NOTHING keeps ingestion idempotent.
    """
    key = "\x00".join([source, str(page_number), content])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _records_from_text(text: str, source: str) -> list[ChunkRecord]:
    """Plain-text document -> chunk records with no page number."""
    return [(chunk, source, i, None) for i, chunk in enumerate(chunk_text(text))]


def _records_from_pages(pages: list[dict], source: str) -> list[ChunkRecord]:
    """OCR'd pages -> chunk records.

    Each page is chunked independently so no chunk spans two pages and each keeps
    its page_number. chunk_index runs across the whole document.
    """
    records: list[ChunkRecord] = []
    chunk_index = 0
    for page in pages:
        page_number = page["page_number"]
        for chunk in chunk_text(page["text"]):
            records.append((chunk, source, chunk_index, page_number))
            chunk_index += 1
    return records


def _store_records(conn, records: list[ChunkRecord]) -> int:
    """Batch-embed and insert records, skipping content_hash duplicates. Returns new rows."""
    if not records:
        return 0

    contents = [content for content, _, _, _ in records]
    embeddings = embed_texts(contents)

    rows = [
        (
            content,
            source,
            chunk_index,
            page_number,
            _content_hash(source, page_number, content),
            _to_vector_literal(embedding),
        )
        for (content, source, chunk_index, page_number), embedding in zip(
            records, embeddings
        )
    ]

    with conn.cursor() as cur:
        # fetch=True collects RETURNING rows across all internal pages, so its
        # length is an accurate new-row count; cur.rowcount only sees the last page.
        returned = execute_values(
            cur,
            """
            INSERT INTO documents
                (content, source, chunk_index, page_number, content_hash, embedding)
            VALUES %s
            ON CONFLICT (content_hash) DO NOTHING
            RETURNING id
            """,
            rows,
            template="(%s, %s, %s, %s, %s, %s::vector)",
            fetch=True,
        )
    conn.commit()
    return len(returned)


def ingest_file(conn, path: str) -> int:
    """Embed and store a plain-text file's chunks (page_number NULL). Returns new rows."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return _store_records(conn, _records_from_text(text, os.path.basename(path)))


def ingest_pages(conn, pages: list[dict], source: str) -> int:
    """Embed and store OCR'd pages, keeping each chunk's page_number. Returns new rows."""
    return _store_records(conn, _records_from_pages(pages, source))


if __name__ == "__main__":
    import sys

    conn = get_connection()
    try:
        init_schema(conn)
        if len(sys.argv) > 1:
            # Usage: python -m src.ingest <pages.json> [source_name]
            from src.pdf_loader import load_extracted_text

            json_path = sys.argv[1]
            source = sys.argv[2] if len(sys.argv) > 2 else os.path.basename(json_path)
            pages = load_extracted_text(json_path)
            n = ingest_pages(conn, pages, source)
            print(
                f"Ingested {n} new chunks from {json_path} "
                f"({len(pages)} pages, source={source!r})"
            )
            # Rebuild the structured parts table for aggregation queries.
            from src.parts import ingest_parts

            n_parts = ingest_parts(conn, pages)
            print(f"Extracted {n_parts} parts into the parts table")
        else:
            n = ingest_file(conn, SAMPLE_DOCS_PATH)
            print(f"Ingested {n} chunks from {SAMPLE_DOCS_PATH}")
    finally:
        conn.close()
