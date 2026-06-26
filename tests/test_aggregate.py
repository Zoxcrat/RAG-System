"""Tests for the text-to-SQL guardrails and self-consistency (pure, no DB or API)."""
from src.answer.aggregate import (
    _AGG_CUE_RE,
    _result_signature,
    _with_limit,
    is_aggregation_query,
    is_safe_select,
)


def test_aggregation_cues_route_without_calling_the_llm(monkeypatch):
    # A clear counting/listing cue must route to AGGREGATE deterministically; the
    # LLM classifier flakes exactly on these, so it must not even be consulted.
    def _boom(*_a, **_k):  # pragma: no cover - asserts the LLM isn't called
        raise AssertionError("LLM classifier should be bypassed on a clear cue")

    monkeypatch.setattr("src.answer.aggregate._chat", _boom)
    for q in (
        "how many ribs per main wing side?",
        "List all adhesives used",
        "what is the most common fastener?",
        "total number of rivets",
    ):
        assert is_aggregation_query(q)


def test_lookup_questions_have_no_aggregation_cue():
    for q in (
        "What is the part number for the radio shelf?",
        "Where is the dorsal assembly listed?",
    ):
        assert not _AGG_CUE_RE.search(q)


# --- run_select transaction hygiene -----------------------------------------

class _FakeCursor:
    def __init__(self, rows, description):
        self._rows, self.description = rows, description

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def execute(self, _sql):
        pass

    def fetchall(self):
        return self._rows


class _FakeConn:
    """Records rollback / set_session order; cursor returns one canned row."""

    def __init__(self):
        self.events = []

    def rollback(self):
        self.events.append("rollback")

    def set_session(self, readonly):
        self.events.append(("set_session", readonly))

    def cursor(self):
        return _FakeCursor([(42,)], [("n",)])


def test_run_select_clears_open_transaction_before_set_session():
    # Regression: set_session() cannot run inside a transaction, so a read left
    # open by a previous caller made every SQL candidate raise and silently fall
    # back. run_select must roll back BEFORE set_session, and restore RW at the end.
    from src.answer.aggregate import run_select

    conn = _FakeConn()
    columns, rows = run_select(conn, "SELECT count(*) FROM parts")

    assert columns == ["n"] and rows == [(42,)]
    assert conn.events[0] == "rollback"
    assert conn.events[1] == ("set_session", True)
    assert conn.events[-1] == ("set_session", False)


def test_accepts_read_only_select_on_parts():
    assert is_safe_select(
        "SELECT description, page_number FROM parts WHERE description ILIKE '%rib%'"
    )
    assert is_safe_select("SELECT COUNT(*) FROM parts WHERE figure ILIKE '%wing%'")


def test_rejects_writes_and_ddl():
    assert not is_safe_select("DELETE FROM parts")
    assert not is_safe_select("UPDATE parts SET description = 'x'")
    assert not is_safe_select("DROP TABLE parts")


def test_rejects_multiple_statements():
    assert not is_safe_select("SELECT 1 FROM parts; DROP TABLE parts")


def test_rejects_queries_against_other_tables():
    assert not is_safe_select("SELECT * FROM documents")
    assert not is_safe_select("SELECT 1")  # no FROM parts


def test_with_limit_adds_only_when_absent():
    assert _with_limit("SELECT * FROM parts", 50).endswith("LIMIT 50")
    assert _with_limit("SELECT * FROM parts LIMIT 5", 50).endswith("LIMIT 5")


def test_result_signature_is_order_independent():
    cols = ["type", "n"]
    a = _result_signature(cols, [("screw", 98), ("rivet", 14)])
    b = _result_signature(cols, [("rivet", 14), ("screw", 98)])  # reordered
    c = _result_signature(cols, [("screw", 99), ("rivet", 14)])  # different count
    assert a == b
    assert a != c
