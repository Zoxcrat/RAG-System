from typing import Optional

from openai import OpenAI

from src import config

EMBEDDING_MODEL = config.EMBEDDING_MODEL
EMBED_BATCH_SIZE = config.EMBED_BATCH_SIZE

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            max_retries=config.OPENAI_MAX_RETRIES,
            timeout=config.OPENAI_TIMEOUT,
        )
    return _client


def embed_text(text: str) -> list[float]:
    response = _get_client().embeddings.create(model=EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed many texts, batching to stay within the API's per-request limits.

    OpenAI's embeddings endpoint accepts at most 2048 inputs per request, so we
    split into batches of EMBED_BATCH_SIZE. Each response's ``index`` is relative
    to its own batch, so we sort within the batch and append in batch order to
    preserve the global input order.
    """
    if not texts:
        return []
    embeddings: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        response = _get_client().embeddings.create(model=EMBEDDING_MODEL, input=batch)
        ordered = sorted(response.data, key=lambda item: item.index)
        embeddings.extend(item.embedding for item in ordered)
    return embeddings
