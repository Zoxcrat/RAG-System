"""Listwise LLM reranking of retrieved candidates. Fails open to the hybrid order."""
import re

from src import config
from src.openai_client import get_client as _get_client

RERANK_MODEL = config.RERANK_MODEL
_SNIPPET_CHARS = 300


def _build_rerank_prompt(query: str, chunks: list[dict]) -> tuple[str, str]:
    system_prompt = (
        "You are a search reranker. Given a question and a list of numbered "
        "passages, decide which passages best help answer the question. Respond "
        "with ONLY a JSON array of the passage numbers, ordered from most to least "
        "relevant (for example [3,1,2]). No prose, no explanation."
    )
    lines = [f"Question: {query}", "", "Passages:"]
    for i, chunk in enumerate(chunks, start=1):
        snippet = (chunk.get("content") or "").replace("\n", " ")[:_SNIPPET_CHARS]
        lines.append(f"[{i}] (page {chunk.get('page_number')}) {snippet}")
    lines.append("")
    lines.append("Ranking (JSON array of passage numbers):")
    return system_prompt, "\n".join(lines)


def _parse_ranking(text: str, n: int) -> list[int]:
    """Parse the model's reply into a full 0-based permutation of range(n).

    Tolerant: keeps valid in-range integers in order without duplicates, then
    appends any omitted passage in its original position, so a malformed ranking
    can never drop a candidate.
    """
    match = re.search(r"\[[^\]]*\]", text)
    source = match.group(0) if match else text
    order: list[int] = []
    for token in re.findall(r"\d+", source):
        idx = int(token) - 1  # prompt numbers passages from 1
        if 0 <= idx < n and idx not in order:
            order.append(idx)
    for idx in range(n):
        if idx not in order:
            order.append(idx)
    return order


def rerank(query: str, chunks: list[dict], top_k: int) -> list[dict]:
    """Reorder ``chunks`` by relevance and return the top_k; keeps input order on error."""
    if not chunks:
        return []

    system_prompt, user_prompt = _build_rerank_prompt(query, chunks)
    try:
        response = _get_client().chat.completions.create(
            model=RERANK_MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        order = _parse_ranking(response.choices[0].message.content or "", len(chunks))
    except Exception:  # noqa: BLE001 - best-effort
        order = list(range(len(chunks)))

    return [chunks[i] for i in order[:top_k]]
