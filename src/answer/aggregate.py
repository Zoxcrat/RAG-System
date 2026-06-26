"""Aggregation answers via text-to-SQL over the structured `parts` table."""
import re
from typing import Optional

from openai import OpenAI

from src import config

LLM_MODEL = config.AGG_MODEL  # stronger model for the SQL/structural reasoning
ROW_LIMIT = config.AGG_ROW_LIMIT
SELF_CONSISTENCY = config.AGG_SELF_CONSISTENCY
SAMPLE_TEMPERATURE = config.AGG_SAMPLE_TEMPERATURE

PARTS_SCHEMA = (
    "parts(part_number TEXT, description TEXT, page_number INTEGER, figure TEXT, "
    "units_per_assy INTEGER, usable_on TEXT, station TEXT, index_no TEXT)"
)

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
        "- description is UPPERCASE OCR text, e.g. 'RIB ASSEMBLY-LH STA 23.625', 'SCREW', 'NUT'.\n"
        "- figure is the assembly/section a part belongs to, e.g. 'Wing Structure Assembly'.\n"
        "- units_per_assy = how many units of that part go in its assembly (the catalog's\n"
        "  physical count). usable_on = serial/model code ('AR' means as-required/bulk).\n"
        "  station = wing station for structural parts (e.g. '23.625'), NULL otherwise.\n"
        "- Use ILIKE with % wildcards for text matching (descriptions vary).\n"
        "- Watch substrings: 'cement' is inside 'reinforcement', so when matching 'cement'\n"
        "  add AND description NOT ILIKE '%reinforcement%'. For 'rib', match descriptions that\n"
        "  start with it or have it as a word: (description ILIKE 'RIB%' OR description ILIKE '% RIB%').\n"
        "- CHOOSE THE MEASURE BY INTENT (this is the key decision):\n"
        "    * physical count / 'how many are there' / 'most common' / totals -> SUM(units_per_assy)\n"
        "      (the catalog's physical units), NOT COUNT(DISTINCT part_number).\n"
        "    * 'how many kinds/types/variants/distinct part numbers' -> COUNT(DISTINCT part_number).\n"
        "    * counting physical positions of a structural part (e.g. ribs) -> COUNT(DISTINCT station).\n"
        "- A part's side appears as '-LH'/' LH' or '-RH'/' RH' anywhere in description; match both\n"
        "  forms: (description ILIKE '%-LH%' OR description ILIKE '% LH%').\n"
        "- Structural counts want a breakdown by SUB-TYPE, not one lumped number. Example —\n"
        "  ribs per wing side broken down (the answer should read like 'N main, M nose, ...'):\n"
        "  SELECT CASE\n"
        "           WHEN description ILIKE '%TRAILING EDGE%' THEN 'trailing-edge'\n"
        "           WHEN description ILIKE '%NOSE%' OR description ILIKE '%LEADING EDGE%' THEN 'nose'\n"
        "           WHEN description ILIKE '%FUEL CELL%' OR description ILIKE '%FUEL TANK%' THEN 'fuel-cell'\n"
        "           ELSE 'main' END AS subtype,\n"
        "         COUNT(DISTINCT station) FILTER (WHERE description ILIKE '%-LH%' OR description ILIKE '% LH%') AS lh,\n"
        "         COUNT(DISTINCT station) FILTER (WHERE description ILIKE '%-RH%' OR description ILIKE '% RH%') AS rh,\n"
        "         (array_agg(DISTINCT page_number))[1:3] AS page_number\n"
        "  FROM parts WHERE figure ILIKE '%wing%' AND (description ILIKE 'RIB%' OR description ILIKE '% RIB%')\n"
        "  GROUP BY subtype ORDER BY subtype\n"
        "- 'List all X' / 'which X are used' is a LISTING, not a count: SELECT part_number,\n"
        "  description, units_per_assy, page_number for the matching rows (DISTINCT part_number),\n"
        "  ORDER BY page_number. Match X AND its near-synonyms/brands, e.g. adhesives also read as\n"
        "  'ADHESIVE','SEALANT','CEMENT','EPOXY' and by spec/brand ('EC','LOCTITE','CONLEY');\n"
        "  combine them with OR (ILIKE), and exclude 'reinforcement' from the 'cement' term.\n"
        "- To scope to a system/section, match figure, e.g. figure ILIKE '%wing%' (figure may be\n"
        "  NULL on some rows; for structural counts you can also rely on station/description).\n"
        "- Always include page_number (or an aggregate of pages) so the answer can cite pages;\n"
        "  for grouped queries use e.g. (array_agg(DISTINCT page_number))[1:3] AS page_number.\n"
        "- 'Most common <category>' means compare the TYPES within that category by PHYSICAL\n"
        "  usage. Example — most common fastener type:\n"
        "  SELECT t.type, SUM(p.units_per_assy) AS physical_units,\n"
        "         COUNT(DISTINCT p.part_number) AS distinct_part_numbers,\n"
        "         (array_agg(DISTINCT p.page_number))[1:3] AS page_number\n"
        "  FROM parts p JOIN unnest(ARRAY['screw','rivet','bolt','nut','washer','pin','clamp'])\n"
        "       AS t(type) ON p.description ILIKE ('%' || t.type || '%')\n"
        "  GROUP BY t.type ORDER BY physical_units DESC NULLS LAST\n"
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
        "Be concise and concrete, and give a structured breakdown when the data has sub-groups. "
        "State the MEASURE the numbers represent, reading it from the column names: "
        "'physical_units' / SUM of units_per_assy = the catalog's units-per-assembly (physical "
        "count); 'distinct_part_numbers' = how many distinct part numbers (catalog variety); "
        "distinct stations = physical positions. Do not call one the other.\n"
        "Honesty about the source (state the relevant caveat when it applies):\n"
        "- A spare-parts catalog UNDER-COUNTS rivets and other as-required hardware: they are "
        "specified per engineering drawing, not fully enumerated per assembly. So if units_per_assy "
        "ranks screws above rivets, say that this reflects the catalog's listings, and note that in "
        "actual airframe construction rivets are the most numerous fastener — the catalog just does "
        "not count them that way.\n"
        "- If the question asks for an attribute the rows do not contain (e.g. screw drive type "
        "Phillips/hex/torx), say the catalog does not specify it; if a type is simply absent, say so.\n"
        "When listing items, include each item's part_number (the question asks for them).\n"
        "Cite pages ONLY from the page_number column, in the EXACT format [page N], each page in its "
        "own brackets, e.g. [page 12] [page 15] (never [page 12, 15]). If there is no page_number "
        "column, cite no pages — never turn a count or any other number into a page. Cite only the "
        "few pages that support the answer. If the results are empty, say you don't have enough "
        "information. Never invent data not in the rows.",
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
