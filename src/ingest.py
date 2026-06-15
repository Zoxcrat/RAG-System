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

# A chunk before embedding: (content, source, chunk_index, page_number).
# page_number is None for plain-text documents that have no pages.
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

    Includes source and page_number (not just the text) so that identical
    boilerplate appearing on different pages — common in a scanned catalog with
    repeated headers/footers — is stored as distinct, citable rows instead of
    collapsing into one. Re-ingesting the same document still yields the same
    hashes, so ingestion stays idempotent via ON CONFLICT DO NOTHING.
    """
    key = "\x00".join([source, str(page_number), content])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _records_from_text(text: str, source: str) -> list[ChunkRecord]:
    """Plain-text document → chunk records with no page number."""
    return [(chunk, source, i, None) for i, chunk in enumerate(chunk_text(text))]


def _records_from_pages(pages: list[dict], source: str) -> list[ChunkRecord]:
    """OCR'd pages → chunk records.

    Each page is chunked independently, so every chunk carries the page_number it
    came from and one chunk never spans two pages — exactly what citing an exact
    page needs. chunk_index runs across the whole document; pages whose OCR text
    is empty contribute nothing.
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
    """Embed every record's content in one batch and insert, skipping duplicates
    by content_hash. Returns the number of NEW rows inserted.
    """
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
        execute_values(
            cur,
            """
            INSERT INTO documents
                (content, source, chunk_index, page_number, content_hash, embedding)
            VALUES %s
            ON CONFLICT (content_hash) DO NOTHING
            """,
            rows,
            template="(%s, %s, %s, %s, %s, %s::vector)",
        )
        inserted = cur.rowcount
    conn.commit()
    return inserted


def ingest_file(conn, path: str) -> int:
    """Embed and store every chunk of a plain-text file. Returns NEW rows.

    Idempotent: chunks already present (same content_hash) are skipped. Plain
    text has no pages, so page_number is stored as NULL.
    """
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return _store_records(conn, _records_from_text(text, os.path.basename(path)))


def ingest_pages(conn, pages: list[dict], source: str) -> int:
    """Embed and store OCR'd pages (a list of {page_number, text} dicts).

    Each chunk keeps the page_number it came from, which is what later lets a
    citation jump to the exact page. Idempotent. Returns the number of NEW rows.
    """
    return _store_records(conn, _records_from_pages(pages, source))


if __name__ == "__main__":
    import sys

    conn = get_connection()
    try:
        init_schema(conn)
        if len(sys.argv) > 1:
            # Ingest OCR'd pages from a JSON produced by src.pdf_loader.
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
        else:
            n = ingest_file(conn, SAMPLE_DOCS_PATH)
            print(f"Ingested {n} chunks from {SAMPLE_DOCS_PATH}")
    finally:
        conn.close()
