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
