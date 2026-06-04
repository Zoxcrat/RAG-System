import os

from src.db import get_connection, init_schema
from src.embed import embed_texts

CHUNK_SIZE = 500
CHUNK_OVERLAP = 100
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


def ingest_file(conn, path: str) -> int:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    chunks = chunk_text(text)
    if not chunks:
        return 0

    embeddings = embed_texts(chunks)
    source = os.path.basename(path)

    with conn.cursor() as cur:
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            cur.execute(
                """
                INSERT INTO documents (content, source, chunk_index, embedding)
                VALUES (%s, %s, %s, %s::vector)
                """,
                (chunk, source, i, _to_vector_literal(embedding)),
            )
    conn.commit()
    return len(chunks)


if __name__ == "__main__":
    conn = get_connection()
    try:
        init_schema(conn)
        n = ingest_file(conn, SAMPLE_DOCS_PATH)
        print(f"Ingested {n} chunks from {SAMPLE_DOCS_PATH}")
    finally:
        conn.close()
