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
    """Vector-only retrieval (kNN by cosine distance). Kept as the semantic arm
    and for comparison; ``ask`` uses :func:`retrieve_hybrid`."""
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

    Matches literal tokens (part numbers, words like HEADLINER) that a dense
    embedding can bury inside a large, noisy chunk. ``websearch_to_tsquery`` is
    forgiving of arbitrary user input. ``distance`` is None: a keyword-only hit
    has no cosine distance, and the relevance gate must stay vector-based.
    """
    with conn.cursor() as cur:
        # OR semantics: rewrite websearch_to_tsquery's default AND ('a & b') into
        # OR ('a | b'). AND is too strict here because chunking by a 500-char window
        # can split a generic term (PART NUMBER header) from the specific one
        # (HANGER HEADLINER row). With OR, ts_rank still ranks chunks matching more
        # terms higher, and the vector arm + relevance gate keep precision.
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
    """Semantic arm: same as :func:`retrieve`, named for symmetry with the hybrid flow."""
    return retrieve(conn, query, top_k=limit)


def reciprocal_rank_fusion(
    ranked_lists: list[list[dict]], top_k: int, rrf_k: int = RRF_K
) -> list[dict]:
    """Fuse several ranked lists into one via Reciprocal Rank Fusion (RRF).

    Score of a document = sum over lists of 1 / (rrf_k + rank), with rank 1-based.
    RRF uses only ranks, not scores, so it combines arms whose scores are not
    comparable (cosine distance vs ts_rank) without any normalization. Documents
    are keyed by id; we keep the variant that carries a cosine distance so the
    relevance gate downstream still has it.
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
    """Hybrid retrieval: fuse a semantic (vector) and a lexical (keyword) arm.

    Each arm returns ``candidates`` results; RRF fuses them into the final top_k.
    This rescues facts that are semantically buried but lexically present (and
    vice versa), which pure vector search misses on dense catalog tables.
    """
    vector_results = _vector_search(conn, query, candidates)
    keyword_results = _keyword_search(conn, query, candidates)
    return reciprocal_rank_fusion([vector_results, keyword_results], top_k)


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
