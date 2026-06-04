import hashlib
import os

from psycopg2.extras import execute_values

from src import config
from src.db import get_connection, init_schema
from src.embed import embed_texts

CHUNK_SIZE = config.CHUNK_SIZE
CHUNK_OVERLAP = config.CHUNK_OVERLAP
SAMPLE_DOCS_PATH = "data/sample_docs.txt"


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


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ingest_file(conn, path: str) -> int:
    """Embed and store every chunk of a file. Returns the number of NEW rows.

    Idempotent: chunks already present (same content_hash) are skipped via
    ON CONFLICT DO NOTHING, so re-running ingestion never creates duplicates.
    """
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    chunks = chunk_text(text)
    if not chunks:
        return 0

    embeddings = embed_texts(chunks)
    source = os.path.basename(path)

    rows = [
        (chunk, source, i, _content_hash(chunk), _to_vector_literal(embedding))
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
    ]

    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO documents (content, source, chunk_index, content_hash, embedding)
            VALUES %s
            ON CONFLICT (content_hash) DO NOTHING
            """,
            rows,
            template="(%s, %s, %s, %s, %s::vector)",
        )
        inserted = cur.rowcount
    conn.commit()
    return inserted


if __name__ == "__main__":
    conn = get_connection()
    try:
        init_schema(conn)
        n = ingest_file(conn, SAMPLE_DOCS_PATH)
        print(f"Ingested {n} chunks from {SAMPLE_DOCS_PATH}")
    finally:
        conn.close()
