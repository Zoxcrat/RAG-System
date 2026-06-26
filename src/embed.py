from src import config
from src.openai_client import get_client as _get_client

EMBEDDING_MODEL = config.EMBEDDING_MODEL
EMBED_BATCH_SIZE = config.EMBED_BATCH_SIZE


def embed_text(text: str) -> list[float]:
    response = _get_client().embeddings.create(model=EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed many texts, batching to stay within the API's per-request limit.

    Each response index is batch-relative, so we sort within the batch and append
    in batch order to preserve global input order.
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
