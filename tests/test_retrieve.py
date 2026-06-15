import src.retrieve as retrieve_mod


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


def test_maps_rows_to_dicts_preserving_order(monkeypatch):
    monkeypatch.setattr(retrieve_mod, "embed_text", lambda q: [0.1, 0.2, 0.3])
    # row = (id, content, source, chunk_index, page_number, distance)
    rows = [
        (1, "content one", "cat.pdf", 0, 42, 0.12),
        (2, "content two", "cat.pdf", 1, 57, 0.34),
    ]

    results = retrieve_mod.retrieve(FakeConn(rows), "q", top_k=2)

    assert results == [
        {"id": 1, "content": "content one", "source": "cat.pdf",
         "chunk_index": 0, "page_number": 42, "distance": 0.12},
        {"id": 2, "content": "content two", "source": "cat.pdf",
         "chunk_index": 1, "page_number": 57, "distance": 0.34},
    ]


def test_result_keys_and_distance_is_float(monkeypatch):
    monkeypatch.setattr(retrieve_mod, "embed_text", lambda q: [1.0])
    rows = [(7, "x", "s", 3, 9, 1)]  # distance given as int -> must be coerced to float

    results = retrieve_mod.retrieve(FakeConn(rows), "q")

    assert set(results[0].keys()) == {
        "id", "content", "source", "chunk_index", "page_number", "distance",
    }
    assert isinstance(results[0]["distance"], float)
    assert results[0]["distance"] == 1.0
    assert results[0]["page_number"] == 9


def test_page_number_can_be_null(monkeypatch):
    # plain-text documents have no page, so page_number comes back as None
    monkeypatch.setattr(retrieve_mod, "embed_text", lambda q: [0.1])
    rows = [(1, "c", "doc.txt", 0, None, 0.2)]

    results = retrieve_mod.retrieve(FakeConn(rows), "q")

    assert results[0]["page_number"] is None


def test_empty_rows_returns_empty_list(monkeypatch):
    monkeypatch.setattr(retrieve_mod, "embed_text", lambda q: [0.5])
    assert retrieve_mod.retrieve(FakeConn([]), "q") == []


def test_passes_query_vector_literal_and_top_k_to_sql(monkeypatch):
    monkeypatch.setattr(retrieve_mod, "embed_text", lambda q: [0.1, 0.2, 0.3])
    conn = FakeConn([])

    retrieve_mod.retrieve(conn, "q", top_k=4)

    sql, params = conn.cursor_obj.executed
    assert params == ("[0.1,0.2,0.3]", 4)
    assert "<=>" in sql
    assert "ORDER BY distance" in sql
    assert "page_number" in sql  # the page rides along with every result
