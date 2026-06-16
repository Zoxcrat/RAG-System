"""Tests for hybrid retrieval: the pure RRF fusion and the keyword SQL arm."""
import src.retrieve as retrieve_mod
from src.retrieve import reciprocal_rank_fusion


def _chunk(cid, distance=None):
    return {"id": cid, "content": f"c{cid}", "source": "cat.pdf",
            "chunk_index": cid, "page_number": cid, "distance": distance}


# --- pure: Reciprocal Rank Fusion -------------------------------------------

def test_rrf_rewards_documents_ranked_by_both_arms():
    vector = [_chunk(1, 0.1), _chunk(2, 0.2)]
    keyword = [_chunk(2), _chunk(3)]

    fused = reciprocal_rank_fusion([vector, keyword], top_k=3, rrf_k=1)

    # id 2 appears in both arms -> highest combined score, ranks first.
    assert [c["id"] for c in fused] == [2, 1, 3]


def test_rrf_respects_top_k():
    vector = [_chunk(1, 0.1), _chunk(2, 0.2), _chunk(3, 0.3)]

    fused = reciprocal_rank_fusion([vector], top_k=2, rrf_k=1)

    assert [c["id"] for c in fused] == [1, 2]


def test_rrf_keeps_variant_carrying_a_distance():
    # keyword arm (distance=None) is seen BEFORE the vector arm for id 5;
    # fusion must keep the vector variant so the gate still has a distance.
    keyword = [_chunk(5, None)]
    vector = [_chunk(5, 0.42)]

    fused = reciprocal_rank_fusion([keyword, vector], top_k=1, rrf_k=1)

    assert fused[0]["id"] == 5
    assert fused[0]["distance"] == 0.42


def test_rrf_empty_lists_return_empty():
    assert reciprocal_rank_fusion([[], []], top_k=5) == []


# --- keyword arm: SQL shape (mocked, no DB) ---------------------------------

class FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.executed = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.executed = (sql, params)

    def fetchall(self):
        return self._rows


class FakeConn:
    def __init__(self, rows):
        self.cursor_obj = FakeCursor(rows)

    def cursor(self):
        return self.cursor_obj


def test_keyword_search_uses_fulltext_and_returns_none_distance():
    rows = [(1, "HANGER-HEADLINER", "cat.pdf", 0, 201)]
    conn = FakeConn(rows)

    results = retrieve_mod._keyword_search(conn, "headliner hanger", limit=20)

    sql, params = conn.cursor_obj.executed
    assert "websearch_to_tsquery" in sql
    assert "tsv @@ q" in sql
    assert "ts_rank" in sql
    assert params == ("headliner hanger", 20)
    # keyword-only hits carry no cosine distance (gate stays vector-based)
    assert results[0]["distance"] is None
    assert results[0]["page_number"] == 201
