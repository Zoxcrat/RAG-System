import src.ingest as ingest_mod
from src.ingest import _content_hash, _records_from_pages, _records_from_text


# --- pure: building chunk records from pages --------------------------------

def test_records_from_pages_attach_page_number_and_running_index():
    pages = [
        {"page_number": 1, "text": "alpha"},
        {"page_number": 2, "text": "beta"},
        {"page_number": 3, "text": "gamma"},
    ]
    records = _records_from_pages(pages, "cat.pdf")

    assert [content for content, *_ in records] == ["alpha", "beta", "gamma"]
    assert [r[1] for r in records] == ["cat.pdf"] * 3   # source
    assert [r[2] for r in records] == [0, 1, 2]         # running chunk_index
    assert [r[3] for r in records] == [1, 2, 3]         # page_number


def test_records_from_pages_running_index_across_multi_chunk_pages():
    text = "x" * 1200  # > CHUNK_SIZE -> several chunks per page at the defaults
    pages = [{"page_number": 7, "text": text}, {"page_number": 8, "text": text}]

    records = _records_from_pages(pages, "s")

    assert len(records) > 2                                   # multiple chunks per page
    assert [r[2] for r in records] == list(range(len(records)))  # one running sequence
    half = len(records) // 2
    assert all(r[3] == 7 for r in records[:half])            # first page's chunks
    assert all(r[3] == 8 for r in records[half:])            # second page's chunks


def test_records_from_pages_skips_pages_without_text():
    pages = [
        {"page_number": 1, "text": ""},
        {"page_number": 2, "text": "   \n  "},
        {"page_number": 3, "text": "real content"},
    ]
    records = _records_from_pages(pages, "s")

    assert len(records) == 1
    assert records[0][0] == "real content"
    assert records[0][2] == 0    # empty pages don't consume a chunk_index
    assert records[0][3] == 3


def test_records_from_text_has_no_page_number():
    records = _records_from_text("hello world", "doc.txt")

    assert len(records) == 1
    content, source, idx, page = records[0]
    assert (content, source, idx, page) == ("hello world", "doc.txt", 0, None)


# --- pure: content hash includes source + page_number -----------------------

def test_content_hash_is_stable():
    assert _content_hash("s", 1, "abc") == _content_hash("s", 1, "abc")


def test_content_hash_distinguishes_page_number():
    # same text on different pages must NOT collide: both have to stay citable
    assert _content_hash("s", 1, "abc") != _content_hash("s", 2, "abc")


def test_content_hash_distinguishes_source():
    assert _content_hash("a.pdf", 1, "abc") != _content_hash("b.pdf", 1, "abc")


def test_content_hash_distinguishes_none_page_from_numbered():
    assert _content_hash("s", None, "abc") != _content_hash("s", 1, "abc")


# --- insert path (mocked embeddings + DB, no API key or database) -----------

class FakeCursor:
    def __init__(self):
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    def __init__(self):
        self.cursor_obj = FakeCursor()
        self.committed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True


def _patch_io(monkeypatch):
    """Mock embeddings and the SQL insert so the test needs no API key or DB.

    Returns a dict that captures the execute_values arguments.
    """
    monkeypatch.setattr(
        ingest_mod, "embed_texts", lambda texts: [[float(i)] for i in range(len(texts))]
    )
    captured = {}

    def fake_execute_values(cur, sql, rows, template=None, fetch=False):
        captured["sql"] = sql
        captured["rows"] = rows
        captured["template"] = template
        cur.rowcount = len(rows)
        # _store_records uses fetch=True + RETURNING to count inserted rows;
        # mimic one RETURNING row per inserted row.
        if fetch:
            return [(i,) for i in range(len(rows))]
        return None

    monkeypatch.setattr(ingest_mod, "execute_values", fake_execute_values)
    return captured


def test_ingest_pages_inserts_page_number_and_returns_new_rows(monkeypatch):
    captured = _patch_io(monkeypatch)
    pages = [
        {"page_number": 4, "text": "first page text"},
        {"page_number": 9, "text": "second page text"},
    ]
    conn = FakeConn()

    n = ingest_mod.ingest_pages(conn, pages, "cat.pdf")

    rows = captured["rows"]
    assert n == 2 == len(rows)
    assert conn.committed is True

    # row = (content, source, chunk_index, page_number, content_hash, vec_literal)
    assert [row[3] for row in rows] == [4, 9]          # page_number flows through
    assert [row[2] for row in rows] == [0, 1]          # running chunk_index
    assert all(row[1] == "cat.pdf" for row in rows)
    for content, source, _idx, page, chash, _vec in rows:
        assert chash == ingest_mod._content_hash(source, page, content)

    assert "page_number" in captured["sql"]
    assert "ON CONFLICT (content_hash) DO NOTHING" in captured["sql"]
    assert "::vector" in captured["template"]


def test_ingest_pages_empty_is_a_noop(monkeypatch):
    captured = _patch_io(monkeypatch)
    called = {"embed": False}
    monkeypatch.setattr(
        ingest_mod, "embed_texts",
        lambda texts: called.__setitem__("embed", True) or [],
    )
    conn = FakeConn()

    n = ingest_mod.ingest_pages(conn, [], "s")

    assert n == 0
    assert called["embed"] is False     # no embedding work for empty input
    assert "rows" not in captured       # execute_values never called
    assert conn.committed is False
