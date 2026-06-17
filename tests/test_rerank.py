"""Tests for the LLM reranker: the pure ranking parser and the reorder/fail-open."""
import src.rerank as rerank_mod
from src.rerank import _parse_ranking, rerank


# --- pure: parsing the model's ranking into a full permutation ---------------

def test_parse_full_ranking_is_zero_based():
    assert _parse_ranking("[3,1,2]", 3) == [2, 0, 1]


def test_parse_appends_omitted_passages_in_order():
    # model only ranked passage 2 -> the rest follow in their original order
    assert _parse_ranking("[2]", 3) == [1, 0, 2]


def test_parse_ignores_out_of_range_and_duplicates():
    assert _parse_ranking("[5, 2, 2, 1]", 3) == [1, 0, 2]


def test_parse_reads_numbers_even_without_a_clean_array():
    assert _parse_ranking("rank: 3 then 1", 3) == [2, 0, 1]


def test_parse_no_numbers_keeps_original_order():
    assert _parse_ranking("none", 3) == [0, 1, 2]


# --- rerank: reorders by the model, truncates to top_k, fails open -----------

class _Msg:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})


class _Resp:
    def __init__(self, content):
        self.choices = [_Msg(content)]


class FakeChat:
    def __init__(self, content=None, raises=False):
        self._content = content
        self._raises = raises

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


def _chunks(n):
    return [{"id": i, "content": f"c{i}", "page_number": i} for i in range(1, n + 1)]


def test_rerank_reorders_and_truncates(monkeypatch):
    monkeypatch.setattr(rerank_mod, "_get_client", lambda: FakeClient(content="[3,1,2]"))

    out = rerank("q", _chunks(3), top_k=2)

    assert [c["id"] for c in out] == [3, 1]   # model order, top-2


def test_rerank_fails_open_on_error(monkeypatch):
    monkeypatch.setattr(rerank_mod, "_get_client", lambda: FakeClient(raises=True))

    out = rerank("q", _chunks(3), top_k=3)

    assert [c["id"] for c in out] == [1, 2, 3]  # original order preserved


def test_rerank_empty_is_noop(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(rerank_mod, "_get_client",
                        lambda: called.__setitem__("n", called["n"] + 1) or FakeClient())

    assert rerank("q", [], top_k=5) == []
    assert called["n"] == 0  # no client call for empty input
