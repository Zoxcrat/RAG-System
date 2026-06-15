from src.db import get_connection
from src.embed import embed_text

DEFAULT_TOP_K = 5


def _to_vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(str(x) for x in embedding) + "]"


def retrieve(conn, query: str, top_k: int = DEFAULT_TOP_K) -> list[dict]:
    query_embedding = embed_text(query)
    vec = _to_vector_literal(query_embedding)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, content, source, chunk_index, page_number,
                   embedding <=> %s::vector AS distance
            FROM documents
            ORDER BY distance
            LIMIT %s
            """,
            (vec, top_k),
        )
        rows = cur.fetchall()

    return [
        {
            "id": row[0],
            "content": row[1],
            "source": row[2],
            "chunk_index": row[3],
            "page_number": row[4],
            "distance": float(row[5]),
        }
        for row in rows
    ]


if __name__ == "__main__":
    conn = get_connection()
    try:
        results = retrieve(conn, "What is PGVector?", top_k=3)
        for r in results:
            page = r["page_number"]
            page_str = f"p.{page}" if page is not None else "p.n/a"
            print(
                f"[{r['distance']:.4f}] {r['source']} ({page_str} #{r['chunk_index']}): "
                f"{r['content'][:80]}..."
            )
    finally:
        conn.close()
