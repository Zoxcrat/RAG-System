"""Aggregation answers via text-to-SQL over the structured `parts` table.

Top-k semantic retrieval can't answer "how many ribs?", "list all X" or "most
common fastener?" — those need to see the whole catalog, not a slice. Since the
catalog is structured data (see src/parts.py), we answer those by:

  1. classifying the question as aggregation vs. lookup (router),
  2. having the LLM write ONE read-only SELECT over `parts` (text-to-SQL),
  3. running it behind strict guardrails (single SELECT, no writes, read-only txn, LIMIT),
  4. having the LLM phrase the answer from the rows, citing pages as [página N].

Guardrails matter: the model writes the SQL, so we never trust it blindly.
"""
import re
from typing import Optional

from openai import OpenAI

from src import config

LLM_MODEL = config.LLM_MODEL
ROW_LIMIT = config.AGG_ROW_LIMIT

PARTS_SCHEMA = "parts(part_number TEXT, description TEXT, page_number INTEGER, figure TEXT)"

# Anything that could mutate state or chain a second statement is rejected outright.
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|grant|revoke|create|copy|merge|into)\b",
    re.IGNORECASE,
)

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(max_retries=config.OPENAI_MAX_RETRIES, timeout=config.OPENAI_TIMEOUT)
    return _client


def _chat(system: str, user: str) -> str:
    resp = _get_client().chat.completions.create(
        model=LLM_MODEL,
        temperature=0,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    return (resp.choices[0].message.content or "").strip()


# --- routing ---------------------------------------------------------------

def is_aggregation_query(query: str) -> bool:
    """True if the question needs aggregation over the whole catalog (count, list
    all, most/least common, totals, grouping) rather than a single fact lookup."""
    answer = _chat(
        "You classify questions about an aircraft parts catalog. Answer with ONE word: "
        "AGGREGATE if the question needs to scan/aggregate the whole catalog (counting, "
        "listing all of something, most/least common, totals, grouping); LOOKUP if it asks "
        "for a single specific fact (a part number, what a part is, where something is).",
        f"Question: {query}",
    )
    return "AGGREGATE" in answer.upper()


# --- text-to-SQL -----------------------------------------------------------

def generate_sql(query: str) -> str:
    sql = _chat(
        "Translate the question into ONE read-only PostgreSQL SELECT over this table:\n"
        f"  {PARTS_SCHEMA}\n"
        "Notes:\n"
        "- description is UPPERCASE OCR text, e.g. 'RIB ASSEMBLY-LH', 'SCREW', 'NUT'.\n"
        "- figure is the assembly/section a part belongs to, e.g. 'Wing Structure Assembly'.\n"
        "- Use ILIKE with % wildcards for text matching (descriptions vary).\n"
        "- To scope to a system, match figure, e.g. figure ILIKE '%wing%'.\n"
        "- For 'most common type' style questions, GROUP BY a keyword and COUNT.\n"
        "- Always include page_number in the SELECT so the answer can cite pages.\n"
        "Return ONLY the SQL: a single SELECT, no semicolon, no markdown, no explanation.",
        f"Question: {query}",
    )
    # strip markdown fences if the model added them
    sql = re.sub(r"```(?:sql)?", "", sql, flags=re.IGNORECASE).replace("```", "").strip()
    return sql


def is_safe_select(sql: str) -> bool:
    """Reject anything that isn't a single read-only SELECT over `parts`."""
    s = sql.strip().rstrip(";").strip()
    if not s or ";" in s:  # exactly one statement
        return False
    if not re.match(r"(?is)^\s*(select|with)\b", s):
        return False
    if _FORBIDDEN.search(s):
        return False
    return bool(re.search(r"(?is)\bfrom\s+parts\b", s))


def _with_limit(sql: str, limit: int) -> str:
    if re.search(r"(?is)\blimit\b", sql):
        return sql
    return f"{sql.rstrip(';').rstrip()} LIMIT {limit}"


def run_select(conn, sql: str) -> tuple[list[str], list[tuple]]:
    """Execute the SELECT in a read-only transaction (defense in depth)."""
    conn.set_session(readonly=True)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            columns = [d[0] for d in cur.description]
            rows = cur.fetchall()
        conn.commit()
        return columns, rows
    finally:
        conn.set_session(readonly=False)


def _format_answer(query: str, columns: list[str], rows: list[tuple]) -> str:
    if rows:
        table = "\n".join(" | ".join(str(c) for c in row) for row in rows[:ROW_LIMIT])
    else:
        table = "(no rows)"
    return _chat(
        "Answer the question using ONLY these SQL results from an aircraft parts catalog. "
        "Be concise and concrete. Cite the relevant page(s) in the EXACT format [página N] "
        "using the page_number column. If the results are empty or don't support an answer, "
        "say you don't have enough information. Never invent data not in the rows.",
        f"Question: {query}\nColumns: {', '.join(columns)}\nRows:\n{table}",
    )


def answer_aggregation(conn, query: str) -> dict:
    """Answer an aggregation question over the parts table.

    Returns ``ok=True`` only when a safe query ran and returned rows. ``ok=False``
    (unsafe SQL, error, or zero rows) signals the caller to fall back to the
    semantic path — e.g. the adhesives live in a column-split materials section the
    parts table doesn't capture, so SQL finds nothing and semantic retrieval wins.
    """
    sql = generate_sql(query)
    if not is_safe_select(sql):
        return {"ok": False, "answer": "", "sql": sql, "pages": []}
    sql = _with_limit(sql, ROW_LIMIT)
    try:
        columns, rows = run_select(conn, sql)
    except Exception:  # noqa: BLE001 - bad generated SQL shouldn't crash the request
        return {"ok": False, "answer": "", "sql": sql, "pages": []}
    if not rows:
        return {"ok": False, "answer": "", "sql": sql, "pages": []}

    answer = _format_answer(query, columns, rows)
    pages = []
    if "page_number" in columns:
        idx = columns.index("page_number")
        pages = sorted({r[idx] for r in rows if isinstance(r[idx], int)})
    return {"ok": True, "answer": answer, "sql": sql, "pages": pages}
