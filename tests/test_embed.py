"""Tests for the embeddings client (mocked: no API key, no network)."""
import src.embed as embed_mod


class FakeDatum:
    """One item of an embeddings response: .index + .embedding."""

    def __init__(self, index: int, embedding: list[float]):
        self.index = index
        self.embedding = embedding


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeEmbeddings:
    def __init__(self, recorder: list[int]):
        self._recorder = recorder

    def create(self, model, input):
        self._recorder.append(len(input))
        # reversed order: embed_texts must sort by .index before returning
        data = [FakeDatum(i, [float(i)]) for i in range(len(input))]
        return FakeResponse(list(reversed(data)))


class FakeClient:
    def __init__(self, recorder: list[int]):
        self.embeddings = FakeEmbeddings(recorder)


def _patch_client(monkeypatch, recorder: list[int]):
    monkeypatch.setattr(embed_mod, "_get_client", lambda: FakeClient(recorder))


def test_embed_texts_empty_makes_no_request(monkeypatch):
    calls: list[int] = []
    _patch_client(monkeypatch, calls)

    assert embed_mod.embed_texts([]) == []
    assert calls == []  # empty input must not hit the API


def test_embed_texts_single_batch_preserves_order(monkeypatch):
    calls: list[int] = []
    _patch_client(monkeypatch, calls)

    out = embed_mod.embed_texts(["a", "b", "c"])

    assert calls == [3]                      # one request for a small input
    assert out == [[0.0], [1.0], [2.0]]      # order restored despite reversed response


def test_embed_texts_splits_into_batches(monkeypatch):
    calls: list[int] = []
    _patch_client(monkeypatch, calls)
    monkeypatch.setattr(embed_mod, "EMBED_BATCH_SIZE", 2)

    out = embed_mod.embed_texts(["a", "b", "c", "d", "e"])

    assert calls == [2, 2, 1]                # batched by size, last batch partial
    assert len(out) == 5                     # every input still gets an embedding
    # batches appended in order; each batch's indices restart at 0
    assert out == [[0.0], [1.0], [0.0], [1.0], [0.0]]


def test_embed_texts_never_exceeds_api_limit(monkeypatch):
    """Stay under the 2048-inputs-per-request cap."""
    calls: list[int] = []
    _patch_client(monkeypatch, calls)

    embed_mod.embed_texts(["x"] * 4500)

    assert all(size <= 2048 for size in calls)  # hard API limit never breached
    assert sum(calls) == 4500                    # and nothing is dropped
