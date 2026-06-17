"""LLM-based reranking of retrieved candidates.

Hybrid retrieval is fast but its ordering is imperfect: a relevant chunk can land
deep in the candidate list (good recall, mediocre rank). A reranker re-scores each
(query, passage) pair jointly — far more accurate than comparing embeddings
separately — and reorders. It is expensive, so it runs only on a small candidate set.

We reuse the chat model as a *listwise* reranker (one call: ask it to order the
numbered passages) instead of pulling in a local cross-encoder (torch) just for this.
The parsing is defensive and the call fails open (keep the hybrid order on any error),
so reranking can only help, never break an answer.
"""
import re
from typing import Optional

from openai import OpenAI

from src import config

RERANK_MODEL = config.RERANK_MODEL
_SNIPPET_CHARS = 300

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            max_retries=config.OPENAI_MAX_RETRIES,
            timeout=config.OPENAI_TIMEOUT,
        )
    return _client


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

    Tolerant by design: reads the integers from the first JSON-looking array (or
    the whole reply), keeps the valid in-range ones in order without duplicates,
    then appends any passage the model omitted in its original position. This way
    a hallucinated, partial, or malformed ranking can never drop a candidate.
    """
    match = re.search(r"\[[^\]]*\]", text)
    source = match.group(0) if match else text
    order: list[int] = []
    for token in re.findall(r"\d+", source):
        idx = int(token) - 1  # the prompt numbers passages from 1
        if 0 <= idx < n and idx not in order:
            order.append(idx)
    for idx in range(n):
        if idx not in order:
            order.append(idx)
    return order


def rerank(query: str, chunks: list[dict], top_k: int) -> list[dict]:
    """Reorder ``chunks`` by relevance to ``query`` and return the top_k.

    Fails open: any API/parse error keeps the input order (truncated to top_k).
    """
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
    except Exception:  # noqa: BLE001 - reranking is best-effort; never break the answer
        order = list(range(len(chunks)))

    return [chunks[i] for i in order[:top_k]]
