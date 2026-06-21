"""Aggregation answers via text-to-SQL over the structured `parts` table."""
import re
from typing import Optional

from openai import OpenAI

from src import config

LLM_MODEL = config.LLM_MODEL
ROW_LIMIT = config.AGG_ROW_LIMIT
SELF_CONSISTENCY = config.AGG_SELF_CONSISTENCY
SAMPLE_TEMPERATURE = config.AGG_SAMPLE_TEMPERATURE

PARTS_SCHEMA = "parts(part_number TEXT, description TEXT, page_number INTEGER, figure TEXT)"

# Reject anything that mutates state or chains a second statement.
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


def _chat(system: str, user: str, temperature: float = 0.0) -> str:
    resp = _get_client().chat.completions.create(
        model=LLM_MODEL,
        temperature=temperature,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    return (resp.choices[0].message.content or "").strip()


# --- routing ---------------------------------------------------------------

def is_aggregation_query(query: str) -> bool:
    """True if the question needs aggregation over the whole catalog vs. a lookup."""
    answer = _chat(
        "You classify questions about an aircraft parts catalog. Answer with ONE word: "
        "AGGREGATE if the question needs to scan/aggregate the whole catalog (counting, "
        "listing all of something, most/least common, totals, grouping); LOOKUP if it asks "
        "for a single specific fact (a part number, what a part is, where something is).",
        f"Question: {query}",
    )
    return "AGGREGATE" in answer.upper()


# --- text-to-SQL -----------------------------------------------------------

def generate_sql(query: str, temperature: float = 0.0) -> str:
    sql = _chat(
        "Translate the question into ONE read-only PostgreSQL SELECT over this table:\n"
        f"  {PARTS_SCHEMA}\n"
        "Notes:\n"
        "- description is UPPERCASE OCR text, e.g. 'RIB ASSEMBLY-LH', 'SCREW', 'NUT'.\n"
        "- figure is the assembly/section a part belongs to, e.g. 'Wing Structure Assembly'.\n"
        "- Use ILIKE with % wildcards for text matching (descriptions vary).\n"
        "- Count parts with COUNT(DISTINCT part_number); never restrict to a single page\n"
        "  unless the question asks about one page.\n"
        "- To scope to a system, match figure, e.g. figure ILIKE '%wing%'.\n"
        "- For 'most common' questions, GROUP BY the relevant keyword across the WHOLE\n"
        "  table and ORDER BY the count DESC (return the top groups, not one page).\n"
        "- Always include page_number (or an aggregate of pages) so the answer can cite pages;\n"
        "  for grouped queries use e.g. (array_agg(DISTINCT page_number))[1:3] AS page_number.\n"
        "- 'Most common <category>' means compare the TYPES within that category, not parts whose\n"
        "  description literally contains the word. Example — most common fastener type:\n"
        "  SELECT t.type, COUNT(DISTINCT p.part_number) AS n,\n"
        "         (array_agg(DISTINCT p.page_number))[1:3] AS page_number\n"
        "  FROM parts p JOIN unnest(ARRAY['screw','rivet','bolt','nut','washer','pin','clamp'])\n"
        "       AS t(type) ON p.description ILIKE '%' || t.type || '%'\n"
        "  GROUP BY t.type ORDER BY n DESC\n"
        "Return ONLY the SQL: a single SELECT, no semicolon, no markdown, no explanation.",
        f"Question: {query}",
        temperature=temperature,
    )
    # strip markdown fences the model may have added
    sql = re.sub(r"```(?:sql)?", "", sql, flags=re.IGNORECASE).replace("```", "").strip()
    return sql


def is_safe_select(sql: str) -> bool:
    """Reject anything that isn't a single read-only SELECT over `parts`."""
    s = sql.strip().rstrip(";").strip()
    if not s or ";" in s:  # single statement only
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
    """Execute the SELECT in a read-only transaction."""
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


def _result_signature(columns: list[str], rows: list[tuple]) -> tuple:
    """Order-independent signature of a result set, for majority voting."""
    return (tuple(columns), tuple(sorted(str(row) for row in rows)))


def _pages_from(columns: list[str], rows: list[tuple]) -> list[int]:
    pages: set = set()
    if "page_number" in columns:
        idx = columns.index("page_number")
        for row in rows:
            value = row[idx]
            if isinstance(value, int):
                pages.add(value)
            elif isinstance(value, (list, tuple)):  # array_agg from grouped queries
                pages.update(v for v in value if isinstance(v, int))
    return sorted(pages)


def answer_aggregation(conn, query: str) -> dict:
    """Answer an aggregation question with self-consistency over sampled SQL.

    Samples several SQL candidates, runs each, and keeps the result the majority
    agree on. ok=False (no safe query ran or empty consensus) tells the caller to
    fall back to the semantic path.
    """
    from collections import Counter

    n = max(1, SELF_CONSISTENCY)
    runs: list[tuple] = []  # (sql, columns, rows)
    for _ in range(n):
        temperature = 0.0 if n == 1 else SAMPLE_TEMPERATURE
        sql = generate_sql(query, temperature=temperature)
        if not is_safe_select(sql):
            continue
        sql = _with_limit(sql, ROW_LIMIT)
        try:
            columns, rows = run_select(conn, sql)
        except Exception:  # noqa: BLE001 - a bad query just doesn't get a vote
            continue
        runs.append((sql, columns, rows))

    if not runs:
        return {"ok": False, "answer": "", "sql": "", "pages": [], "agreement": "0/0"}

    votes = Counter(_result_signature(c, r) for _, c, r in runs)
    winning_sig, agree = votes.most_common(1)[0]
    sql, columns, rows = next(
        (s, c, r) for s, c, r in runs if _result_signature(c, r) == winning_sig
    )
    agreement = f"{agree}/{len(runs)}"

    if not rows:
        return {"ok": False, "answer": "", "sql": sql, "pages": [], "agreement": agreement}

    answer = _format_answer(query, columns, rows)
    return {
        "ok": True,
        "answer": answer,
        "sql": sql,
        "pages": _pages_from(columns, rows),
        "agreement": agreement,
    }
