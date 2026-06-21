"""Tests for the text-to-SQL guardrails and self-consistency (pure, no DB or API)."""
from src.aggregate import _result_signature, _with_limit, is_safe_select


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
    b = _result_signature(cols, [("rivet", 14), ("screw", 98)])  # same rows, different order
    c = _result_signature(cols, [("screw", 99), ("rivet", 14)])  # different count
    assert a == b   # voting treats these as the same result
    assert a != c
