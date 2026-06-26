"""End-to-end answer-quality eval over a typed question set.

Runs the full ``ask()`` pipeline (routing -> aggregation/semantic -> generation)
and grades each answer against ground truth verified from the catalog data:
assertions, not an LLM judge, so the score is deterministic and explainable.

Reports a pass rate per question type and overall, plus per-item PASS/FAIL with
the first failing check.

Run: docker compose run --rm --entrypoint python app -m eval.evaluate_answers
     (or, locally: .venv/bin/python -m eval.evaluate_answers)
"""
import json

from src.db import get_connection
from src.answer.rag import ask

ANSWER_SET = json.load(open("eval/answer_set.json", encoding="utf-8"))["items"]

# Substrings the gate / generator use when it declines to answer.
_REFUSAL_MARKERS = ("don't have enough", "do not have enough", "not enough information")


def _contains(haystack: str, needle: str) -> bool:
    return needle.lower() in haystack.lower()


def _is_refusal(answer: str) -> bool:
    return any(_contains(answer, m) for m in _REFUSAL_MARKERS)


def grade(item: dict, result: dict) -> tuple[bool, str]:
    """Return (passed, reason). reason names the first failing check, or 'ok'."""
    answer = result.get("answer", "")

    if item.get("must_refuse"):
        return (True, "ok") if _is_refusal(answer) else (False, "did not refuse")

    # A refusal on an in-domain question is always a failure.
    if _is_refusal(answer):
        return False, "refused an in-domain question"

    expected_mode = item.get("expected_mode")
    if expected_mode and result.get("mode") != expected_mode:
        return False, f"mode={result.get('mode')} (expected {expected_mode})"

    for needle in item.get("must_include", []):
        if not _contains(answer, needle):
            return False, f"missing {needle!r}"

    for group in item.get("must_include_any", []):
        if not any(_contains(answer, opt) for opt in group):
            return False, f"none of {group} present"

    # A part can be listed on several pages; citing ANY page that legitimately
    # contains it is correct, so require a non-empty intersection, not a subset.
    expect_pages = set(item.get("expect_pages", []))
    cited = set(result.get("pages", []))
    if expect_pages and not (expect_pages & cited):
        return False, f"pages {sorted(cited)} miss all of {sorted(expect_pages)}"

    return True, "ok"


def main() -> None:
    conn = get_connection()
    try:
        rows = []
        for item in ANSWER_SET:
            result = ask(conn, item["question"])
            passed, reason = grade(item, result)
            rows.append((item["type"], item["question"], passed, reason))
    finally:
        conn.close()

    by_type: dict[str, list[bool]] = {}
    for qtype, _q, passed, _r in rows:
        by_type.setdefault(qtype, []).append(passed)

    print(f"\n=== Answer quality on {len(rows)} questions ===")
    print(f"{'type':<14}{'pass':>8}{'total':>8}{'rate':>8}")
    for qtype in sorted(by_type):
        results = by_type[qtype]
        n_pass = sum(results)
        print(f"{qtype:<14}{n_pass:>8}{len(results):>8}{n_pass / len(results):>8.2f}")
    total_pass = sum(p for *_x, p, _r in rows)
    print("-" * 38)
    print(f"{'overall':<14}{total_pass:>8}{len(rows):>8}{total_pass / len(rows):>8.2f}")

    print("\n=== per-question ===")
    for qtype, q, passed, reason in rows:
        mark = "PASS" if passed else "FAIL"
        tail = "" if passed else f"  <- {reason}"
        print(f"  [{mark}] ({qtype}) {q[:58]}{tail}")


if __name__ == "__main__":
    main()
