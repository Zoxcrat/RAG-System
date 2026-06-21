"""Query expansion (multi-query / RAG-Fusion).

If a question is worded differently from the catalog ("what holds the headliner up?"
vs the catalog's "HANGER-HEADLINER"), a single query can miss. We ask the LLM for a
few paraphrases, retrieve for each, and fuse the results (see retrieve.retrieve_multi).
More angles on the same question = more robust recall, at the cost of a few extra
retrievals.
"""
from typing import Optional

from openai import OpenAI

from src import config

LLM_MODEL = config.LLM_MODEL
EXPANSION_N = config.QUERY_EXPANSION_N

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(max_retries=config.OPENAI_MAX_RETRIES, timeout=config.OPENAI_TIMEOUT)
    return _client


def expand_query(query: str, n: int = EXPANSION_N) -> list[str]:
    """Return up to ``n`` query variants, always including the original first.

    Fails open: any error returns just the original query, so expansion can only
    help recall, never break a request.
    """
    if n <= 1:
        return [query]
    try:
        resp = _get_client().chat.completions.create(
            model=LLM_MODEL,
            temperature=0.3,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Rewrite the user's question about an aircraft parts catalog into "
                        f"{n - 1} alternative phrasings that a parts catalog might use "
                        "(synonyms, technical terms, the part's function). One per line, no "
                        "numbering, no extra text."
                    ),
                },
                {"role": "user", "content": query},
            ],
        )
        text = resp.choices[0].message.content or ""
    except Exception:  # noqa: BLE001 - expansion is best-effort
        return [query]

    variants = [query]
    for line in text.splitlines():
        candidate = line.strip().lstrip("-•0123456789. ").strip()
        if candidate and candidate.lower() != query.lower():
            variants.append(candidate)
    return variants[:n]
