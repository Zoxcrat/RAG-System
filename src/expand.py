"""Query expansion (multi-query / RAG-Fusion): LLM paraphrases of the question."""
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
    """Return up to ``n`` query variants, original first; returns just the original on error."""
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
    except Exception:  # noqa: BLE001 - best-effort
        return [query]

    variants = [query]
    for line in text.splitlines():
        candidate = line.strip().lstrip("-•0123456789. ").strip()
        if candidate and candidate.lower() != query.lower():
            variants.append(candidate)
    return variants[:n]
