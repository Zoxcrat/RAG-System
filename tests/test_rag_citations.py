import src.rag as rag


# --- build_prompt: pages are exposed and page citations are requested --------

def test_build_prompt_shows_page_and_asks_for_page_citation():
    chunks = [
        {"content": "wing bolt P/N 0500", "source": "cat.pdf", "page_number": 42,
         "distance": 0.1},
        {"content": "tail rivet", "source": "cat.pdf", "page_number": 57,
         "distance": 0.2},
    ]

    system_prompt, user_prompt = rag.build_prompt("which bolt?", chunks)

    # the model is told to cite in the exact [página N] format (frontend parses it)
    assert "[página N]" in system_prompt
    # each chunk carries its page in the context
    assert 'page="42"' in user_prompt
    assert 'page="57"' in user_prompt
    assert "wing bolt P/N 0500" in user_prompt
    assert user_prompt.endswith("Question: which bolt?")


def test_build_prompt_handles_chunk_without_page():
    chunks = [{"content": "x", "source": "doc.txt"}]  # plain text, no page_number

    _system, user_prompt = rag.build_prompt("q", chunks)

    assert 'page="n/a"' in user_prompt


# --- ask: assembles sources with page_number and the unique pages used -------

def _patch_pipeline(monkeypatch, chunks, answer="ok"):
    # these tests cover the lookup path, so force the aggregation router off
    monkeypatch.setattr(rag, "is_aggregation_query", lambda query: False)
    monkeypatch.setattr(rag, "retrieve_hybrid", lambda conn, query, top_k: chunks)
    # rerank is exercised in test_rerank; here use an identity passthrough so the
    # ask() assertions stay focused on response assembly (no API call).
    monkeypatch.setattr(rag, "rerank", lambda query, c, top_k: c[:top_k])
    monkeypatch.setattr(rag, "generate_answer", lambda query, c: answer)


def test_ask_returns_sources_with_page_and_unique_sorted_pages(monkeypatch):
    chunks = [
        {"id": 10, "content": "a", "source": "cat.pdf", "chunk_index": 0,
         "page_number": 57, "distance": 0.1},
        {"id": 11, "content": "b", "source": "cat.pdf", "chunk_index": 1,
         "page_number": 42, "distance": 0.2},
        {"id": 12, "content": "c", "source": "cat.pdf", "chunk_index": 2,
         "page_number": 42, "distance": 0.3},  # same page as above -> deduped
    ]
    _patch_pipeline(monkeypatch, chunks, answer="Use the bolt [página 42]")

    out = rag.ask(object(), "q")

    assert out["answer"] == "Use the bolt [página 42]"
    assert out["pages"] == [42, 57]                       # unique + sorted
    assert [s["page_number"] for s in out["sources"]] == [57, 42, 42]
    assert all("page_number" in s for s in out["sources"])
    assert out["min_distance"] == 0.1


def test_ask_pages_excludes_null_pages(monkeypatch):
    chunks = [
        {"id": 1, "content": "a", "source": "doc.txt", "chunk_index": 0,
         "page_number": None, "distance": 0.1},
        {"id": 2, "content": "b", "source": "cat.pdf", "chunk_index": 1,
         "page_number": 5, "distance": 0.2},
    ]
    _patch_pipeline(monkeypatch, chunks)

    out = rag.ask(object(), "q")

    assert out["pages"] == [5]


def test_ask_with_no_chunks_has_empty_pages(monkeypatch):
    _patch_pipeline(monkeypatch, [], answer="not enough information")

    out = rag.ask(object(), "q")

    assert out["pages"] == []
    assert out["sources"] == []
    assert out["min_distance"] is None
