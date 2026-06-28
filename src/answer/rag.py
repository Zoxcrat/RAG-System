import re
from typing import Optional

from src import config
from src.answer.aggregate import answer_aggregation, is_aggregation_query
from src.db import get_connection
from src.openai_client import get_client as _get_client
from src.retrieval.rerank import rerank
from src.retrieval.retrieve import retrieve_hybrid

AGG_ENABLED = config.AGG_ENABLED
LLM_MODEL = config.LLM_MODEL
DEFAULT_TOP_K = config.DEFAULT_TOP_K
TEMPERATURE = config.TEMPERATURE
MAX_TOKENS = config.MAX_TOKENS
RELEVANCE_THRESHOLD = config.RELEVANCE_THRESHOLD
RERANK_ENABLED = config.RERANK_ENABLED
RERANK_CANDIDATES = config.RERANK_CANDIDATES


def build_prompt(query: str, chunks: list[dict]) -> tuple[str, str]:
    system_prompt = (
        "You are a precise assistant that answers questions using ONLY the "
        "context provided in the <context> block. Follow these rules strictly:\n"
        "1. Use only information found in the context. Do not rely on prior knowledge.\n"
        "2. If the context does not contain enough information to answer, say so "
        "explicitly and state that you don't have enough information.\n"
        "3. Cite the page(s) you use in the exact format [page N], where N is the "
        "page shown for the chunk you used. Put each page in its own brackets, e.g. "
        "[page 12] [page 15] (never [page 12, 15]).\n"
        "4. Never invent facts, pages, or citations."
    )

    lines: list[str] = ["<context>"]
    for chunk in chunks:
        source = chunk.get("source", "unknown")
        page = chunk.get("page_number")
        page_str = str(page) if page is not None else "n/a"
        content = chunk.get("content", "")
        lines.append(f'<chunk page="{page_str}" source="{source}">')
        lines.append(content)
        lines.append("</chunk>")
    lines.append("</context>")
    context_block = "\n".join(lines)

    user_prompt = f"{context_block}\n\nQuestion: {query}"
    return system_prompt, user_prompt


def _min_distance(chunks: list[dict]) -> Optional[float]:
    """Smallest cosine distance among chunks that have one (keyword-only chunks skipped)."""
    distances = [c["distance"] for c in chunks if c.get("distance") is not None]
    return min(distances) if distances else None


def _pages_used(chunks: list[dict]) -> list[int]:
    """Unique, sorted page numbers offered as context (NULL pages skipped)."""
    return sorted(
        {chunk["page_number"] for chunk in chunks if chunk.get("page_number") is not None}
    )


_PAGE_CITATION_RE = re.compile(r"\[(?:p[aá]gina|page)s?\s+([\d,\s]+)\]", re.IGNORECASE)


def _cited_pages(answer: str) -> list[int]:
    """Page numbers the answer actually cites (handles [page 5] and [page 5, 7])."""
    pages: set[int] = set()
    for group in _PAGE_CITATION_RE.findall(answer):
        pages.update(int(n) for n in re.findall(r"\d+", group))
    return sorted(pages)


def generate_answer(query: str, chunks: list[dict]) -> str:
    min_dist = _min_distance(chunks)

    if not chunks or (min_dist is not None and min_dist > RELEVANCE_THRESHOLD):
        best = "n/a" if min_dist is None else f"{min_dist:.4f}"
        return (
            "I don't have enough information in the context to answer that "
            f"question. (best distance: {best}, threshold: {RELEVANCE_THRESHOLD})"
        )

    system_prompt, user_prompt = build_prompt(query, chunks)

    try:
        response = _get_client().chat.completions.create(
            model=LLM_MODEL,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as e:
        return f"There was an error generating the answer: {e}"


def ask(conn, query: str, top_k: int = DEFAULT_TOP_K) -> dict:
    # Route aggregation questions to the parts table via text-to-SQL.
    if AGG_ENABLED and is_aggregation_query(query):
        agg = answer_aggregation(conn, query)
        # Fall through to semantic retrieval if SQL returned no rows.
        if agg["ok"]:
            return {
                "query": query,
                "answer": agg["answer"],
                "sources": [],
                "pages": _cited_pages(agg["answer"]) or agg["pages"],
                "min_distance": None,
                "mode": "aggregate",
                "sql": agg.get("sql"),
            }

    # Retrieve a wider candidate set, then rerank down to top_k. Gate on candidates
    # first so out-of-domain queries are refused before reranking.
    candidates = retrieve_hybrid(conn, query, top_k=RERANK_CANDIDATES)
    min_dist = _min_distance(candidates)
    relevant = min_dist is not None and min_dist <= RELEVANCE_THRESHOLD

    if RERANK_ENABLED and relevant:
        chunks = rerank(query, candidates, top_k)
    else:
        chunks = candidates[:top_k]

    answer = generate_answer(query, chunks)

    sources = [
        {
            "id": i,
            "source": chunk.get("source"),
            "chunk_index": chunk.get("chunk_index"),
            "page_number": chunk.get("page_number"),
            "distance": chunk.get("distance"),
        }
        for i, chunk in enumerate(chunks, start=1)
    ]

    return {
        "query": query,
        "answer": answer,
        "sources": sources,
        "pages": _cited_pages(answer) or _pages_used(chunks),
        "min_distance": _min_distance(chunks),
        "mode": "lookup",
        "sql": None,
    }


if __name__ == "__main__":
    # First two match the sample docs; the third is off-topic.
    queries = [
        "What is PGVector and what is it used for?",
        "How does retrieval-augmented generation work?",
        "How do I make a pizza from scratch?",
    ]

    conn = get_connection()
    try:
        for query in queries:
            result = ask(conn, query)
            print("=" * 70)
            print(f"Q: {result['query']}")
            print("-" * 70)
            print(f"A: {result['answer']}")
            print("-" * 70)
            md = result["min_distance"]
            print(f"min_distance: {md:.4f}" if md is not None else "min_distance: n/a")
            if result["pages"]:
                print(f"pages: {', '.join(str(p) for p in result['pages'])}")
            print("sources:")
            for s in result["sources"]:
                dist = s["distance"]
                dist_str = f"{dist:.4f}" if dist is not None else "n/a"
                page = s["page_number"]
                page_str = f"p.{page}" if page is not None else "p.n/a"
                print(
                    f"  [{s['id']}] {s['source']} ({page_str}, chunk {s['chunk_index']}) "
                    f"distance={dist_str}"
                )
        print("=" * 70)
    finally:
        conn.close()
