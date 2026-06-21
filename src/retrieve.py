from src import config
from src.db import get_connection
from src.embed import embed_text

DEFAULT_TOP_K = config.DEFAULT_TOP_K
RETRIEVAL_CANDIDATES = config.RETRIEVAL_CANDIDATES
RRF_K = config.RRF_K


def _to_vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(str(x) for x in embedding) + "]"


def _row_to_dict(row, distance) -> dict:
    return {
        "id": row[0],
        "content": row[1],
        "source": row[2],
        "chunk_index": row[3],
        "page_number": row[4],
        "distance": distance,
    }


def retrieve(conn, query: str, top_k: int = DEFAULT_TOP_K) -> list[dict]:
    """Vector-only retrieval (kNN by cosine distance)."""
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

    return [_row_to_dict(row, float(row[5])) for row in rows]


def _keyword_search(conn, query: str, limit: int) -> list[dict]:
    """Lexical arm: Postgres full-text search over the generated ``tsv`` column.

    distance is None: a keyword-only hit has no cosine distance, and the relevance
    gate stays vector-based.
    """
    with conn.cursor() as cur:
        # Rewrite the default AND into OR: 500-char chunking can split a generic
        # term from the specific one, and AND would miss those. ts_rank still
        # ranks chunks matching more terms higher.
        cur.execute(
            """
            WITH q AS (
                SELECT replace(
                    websearch_to_tsquery('english', %s)::text, '&', '|'
                )::tsquery AS query
            )
            SELECT id, content, source, chunk_index, page_number
            FROM documents, q
            WHERE q.query <> '' AND tsv @@ q.query
            ORDER BY ts_rank(tsv, q.query) DESC
            LIMIT %s
            """,
            (query, limit),
        )
        rows = cur.fetchall()

    return [_row_to_dict(row, None) for row in rows]


def _vector_search(conn, query: str, limit: int) -> list[dict]:
    """Semantic arm; alias of :func:`retrieve` for symmetry with the hybrid flow."""
    return retrieve(conn, query, top_k=limit)


def reciprocal_rank_fusion(
    ranked_lists: list[list[dict]], top_k: int, rrf_k: int = RRF_K
) -> list[dict]:
    """Fuse ranked lists via Reciprocal Rank Fusion: score = sum(1 / (rrf_k + rank)).

    Uses ranks only, so it combines arms with incomparable scores (cosine vs
    ts_rank) without normalization. Keyed by id, keeping the variant that carries
    a cosine distance for the downstream relevance gate.
    """
    scores: dict = {}
    payload: dict = {}
    for results in ranked_lists:
        for rank, chunk in enumerate(results, start=1):
            cid = chunk["id"]
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (rrf_k + rank)
            keep = payload.get(cid)
            if keep is None or (
                keep.get("distance") is None and chunk.get("distance") is not None
            ):
                payload[cid] = chunk
    ranked_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)
    return [payload[cid] for cid in ranked_ids[:top_k]]


def retrieve_hybrid(
    conn,
    query: str,
    top_k: int = DEFAULT_TOP_K,
    candidates: int = RETRIEVAL_CANDIDATES,
) -> list[dict]:
    """Hybrid retrieval: fuse the vector and keyword arms with RRF into top_k.

    Rescues facts that are semantically buried but lexically present, and vice versa.
    """
    vector_results = _vector_search(conn, query, candidates)
    keyword_results = _keyword_search(conn, query, candidates)
    return reciprocal_rank_fusion([vector_results, keyword_results], top_k)


def retrieve_multi(
    conn,
    query: str,
    top_k: int = DEFAULT_TOP_K,
    candidates: int = RETRIEVAL_CANDIDATES,
) -> list[dict]:
    """Multi-query (RAG-Fusion): expand into a few phrasings, retrieve hybrid for
    each, and fuse with RRF. Falls back to ``retrieve_hybrid`` for a single query.
    """
    from src.expand import expand_query

    queries = expand_query(query)
    if len(queries) <= 1:
        return retrieve_hybrid(conn, query, top_k=top_k, candidates=candidates)
    ranked_lists = [
        retrieve_hybrid(conn, q, top_k=candidates, candidates=candidates) for q in queries
    ]
    return reciprocal_rank_fusion(ranked_lists, top_k)


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
