from types import SimpleNamespace
from unittest.mock import MagicMock

import src.rag as rag


def _fake_response(content):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _relevant_chunks():
    return [{"content": "ctx", "source": "doc.txt", "chunk_index": 0, "distance": 0.2}]


def test_refuses_when_no_chunks_without_calling_llm(monkeypatch):
    fake_client = MagicMock()
    monkeypatch.setattr(rag, "_get_client", lambda: fake_client)

    out = rag.generate_answer("q", [])

    assert "enough information" in out
    assert "n/a" in out
    fake_client.chat.completions.create.assert_not_called()


def test_refuses_when_min_distance_above_threshold(monkeypatch):
    fake_client = MagicMock()
    monkeypatch.setattr(rag, "_get_client", lambda: fake_client)
    chunks = [{"content": "c", "source": "s", "chunk_index": 0, "distance": 0.9}]

    out = rag.generate_answer("q", chunks)

    assert "0.9000" in out  # best distance surfaced for debugging
    assert str(rag.RELEVANCE_THRESHOLD) in out
    fake_client.chat.completions.create.assert_not_called()


def test_calls_llm_when_below_threshold_and_returns_stripped_content(monkeypatch):
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_response("  Respuesta [1]  ")
    monkeypatch.setattr(rag, "_get_client", lambda: fake_client)

    out = rag.generate_answer("q", _relevant_chunks())

    assert out == "Respuesta [1]"
    fake_client.chat.completions.create.assert_called_once()
    kwargs = fake_client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == rag.LLM_MODEL
    assert kwargs["temperature"] == rag.TEMPERATURE
    assert kwargs["max_tokens"] == rag.MAX_TOKENS
    assert [m["role"] for m in kwargs["messages"]] == ["system", "user"]


def test_threshold_boundary_is_inclusive(monkeypatch):
    # distance exactly == threshold is NOT > threshold, so it must call the LLM
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_response("ok")
    monkeypatch.setattr(rag, "_get_client", lambda: fake_client)
    chunks = [{"content": "c", "source": "s", "chunk_index": 0,
               "distance": rag.RELEVANCE_THRESHOLD}]

    out = rag.generate_answer("q", chunks)

    assert out == "ok"
    fake_client.chat.completions.create.assert_called_once()


def test_llm_error_returns_friendly_message_without_crashing(monkeypatch):
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = RuntimeError("boom")
    monkeypatch.setattr(rag, "_get_client", lambda: fake_client)

    out = rag.generate_answer("q", _relevant_chunks())

    assert out.startswith("There was an error")
    assert "boom" in out
