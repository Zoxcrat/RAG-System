"""Tests for query expansion (mocked LLM, no network)."""
import src.retrieval.expand as expand_mod
from src.retrieval.expand import expand_query


class _Resp:
    def __init__(self, content):
        self.choices = [type("C", (), {"message": type("M", (), {"content": content})})]


class FakeChat:
    def __init__(self, content=None, raises=False):
        self._content, self._raises = content, raises

    @property
    def completions(self):
        return self

    def create(self, model, temperature, messages):
        if self._raises:
            raise RuntimeError("boom")
        return _Resp(self._content)


class FakeClient:
    def __init__(self, content=None, raises=False):
        self.chat = FakeChat(content, raises)


def test_original_is_first_and_variants_parsed(monkeypatch):
    monkeypatch.setattr(
        expand_mod, "_get_client",
        lambda: FakeClient("1. headliner hanger\n- what holds the ceiling up"),
    )
    out = expand_query("headliner support", n=3)

    assert out[0] == "headliner support"          # original always first
    assert "headliner hanger" in out              # numbering/bullets stripped
    assert len(out) <= 3                           # capped at n


def test_n_of_one_skips_the_call():
    assert expand_query("anything", n=1) == ["anything"]


def test_fails_open_to_original(monkeypatch):
    monkeypatch.setattr(expand_mod, "_get_client", lambda: FakeClient(raises=True))
    assert expand_query("anything", n=3) == ["anything"]
