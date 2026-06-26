"""Single process-wide OpenAI client.

Embeddings, chat, reranking and aggregation all share one lazily-built client so
the retry/timeout policy lives in one place instead of being copy-pasted per
module. Modules import this as ``_get_client`` so tests can still monkeypatch the
client on the module that uses it.
"""
from typing import Optional

from openai import OpenAI

from src import config

_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            max_retries=config.OPENAI_MAX_RETRIES,
            timeout=config.OPENAI_TIMEOUT,
        )
    return _client
