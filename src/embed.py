from typing import Optional

from openai import OpenAI

from src import config

EMBEDDING_MODEL = config.EMBEDDING_MODEL

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
    if not texts:
        return []
    response = _get_client().embeddings.create(model=EMBEDDING_MODEL, input=texts)
    ordered = sorted(response.data, key=lambda item: item.index)
    return [item.embedding for item in ordered]
