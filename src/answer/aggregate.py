"""Aggregation answers via text-to-SQL over the structured `parts` table."""
import re

from src import config
from src.openai_client import get_client as _get_client

LLM_MODEL = config.AGG_MODEL  # stronger model for the SQL/structural reasoning
ROW_LIMIT = config.AGG_ROW_LIMIT
SELF_CONSISTENCY = config.AGG_SELF_CONSISTENCY
SAMPLE_TEMPERATURE = config.AGG_SAMPLE_TEMPERATURE

PARTS_SCHEMA = (
    "parts(part_number TEXT, description TEXT, page_number INTEGER, figure TEXT, "
    "units_per_assy INTEGER, usable_on TEXT, station TEXT, index_no TEXT, "
    "station_num DOUBLE PRECISION, side TEXT, part_category TEXT, sub_type TEXT, "
    "variant TEXT)"
)

# Reject anything that mutates state or chains a second statement.
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|grant|revoke|create|copy|merge|into)\b",
    re.IGNORECASE,
)


def _chat(system: str, user: str, temperature: float = 0.0) -> str:
    resp = _get_client().chat.completions.create(
        model=LLM_MODEL,
        temperature=temperature,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    return (resp.choices[0].message.content or "").strip()


# --- routing ---------------------------------------------------------------

# Unambiguous aggregation cues. Routing is biased toward AGGREGATE on purpose:
# the two failure modes are asymmetric. A lookup misrouted to aggregation
# self-corrects (empty SQL -> ok=False -> semantic fallback), but an aggregation
# question misrouted to lookup does not — it just retrieves a few chunks and
# answers "not enough info". So when a clear counting/listing cue is present we
# skip the LLM classifier entirely (it flakes exactly here, e.g. reading "how
# many ribs per side" as a lookup).
_AGG_CUE_RE = re.compile(
    r"\b(how many|how much|how often|number of|total (number|count|amount|quantity)|"
    r"count (of|the)|list (all|every|each|the)|all (the )?(adhesives|sealants|"
    r"fasteners|screws|parts|bolts|rivets)|(most|least) (common|used|frequent|"
    r"numerous|popular)|which .+ (are|is) used)\b",
    re.IGNORECASE,
)


def is_aggregation_query(query: str) -> bool:
    """True if the question needs aggregation over the whole catalog vs. a lookup."""
    if _AGG_CUE_RE.search(query):
        return True
    answer = _chat(
        "You classify questions about an aircraft parts catalog. Answer with ONE word: "
        "AGGREGATE if the question needs to scan or aggregate across the catalog (counting, "
        "listing all of something, most/least common, totals, grouping, comparing usage); "
        "LOOKUP only if it asks for ONE specific fact about ONE part (its part number, what a "
        "single part is, where one thing is listed). When unsure, answer AGGREGATE.\n"
        "Examples:\n"
        "Q: how many ribs per main wing side? -> AGGREGATE\n"
        "Q: list all adhesives used -> AGGREGATE\n"
        "Q: what is the most common fastener? -> AGGREGATE\n"
        "Q: what is the part number for the radio shelf? -> LOOKUP\n"
        "Q: where is the dorsal assembly listed? -> LOOKUP",
        f"Question: {query}",
    )
    return "AGGREGATE" in answer.upper()


# --- text-to-SQL -----------------------------------------------------------

# A data dictionary (what the columns mean and contain) + the measure-selection
# principle + two adaptable patterns, rather than one hard-coded SQL per known
# question. The vocabulary (figure sections, material brands, usable_on codes)
# lets the model scope and match questions it has not seen, not just the three
# challenge ones.
_SQL_SYSTEM = (
    "Translate the question into ONE read-only PostgreSQL SELECT over this table:\n"
    f"  {PARTS_SCHEMA}\n"
    "\n"
    "DATA DICTIONARY\n"
    "- description: UPPERCASE OCR part name, e.g. 'RIB ASSEMBLY-LH STA 23.625', 'SCREW',\n"
    "  'NUT', 'EC2216B/A ADHESIVE'. Match with ILIKE and % wildcards (wording varies).\n"
    "- figure: the section/assembly a part belongs to, for scoping (88 distinct values),\n"
    "  e.g. 'Wing Structure Assembly', 'Fuel System Installation', 'Instrument Panel\n"
    "  Equipment Installation', 'Main Landing Gear Installation', 'Engine Cowl Assembly',\n"
    "  'Brake System Installation', 'Firewall Assembly'. Scope with figure ILIKE\n"
    "  '%keyword%'; figure may be NULL on some rows.\n"
    "- units_per_assy: physical units of that part per assembly (the catalog's real count).\n"
    "- usable_on: serial/model applicability code (A, B, C, ...; 'AR' = as-required/bulk).\n"
    "- station: raw wing-station string ('23.625'); prefer station_num for counting.\n"
    "\n"
    "TYPED COLUMNS (classified once at ingest — PREFER THESE over ILIKE on description)\n"
    "- station_num DOUBLE PRECISION: the wing station as a number, with OCR/format variants\n"
    "  collapsed ('100', '100.00', '100.50' -> 100.0, 100.0, 100.5). COUNT physical positions\n"
    "  with COUNT(DISTINCT station_num), never COUNT(DISTINCT station).\n"
    "- side TEXT: 'LH' / 'RH' / NULL.\n"
    "- part_category TEXT: 'rib','rivet','screw','bolt','nutplate','nut','washer','pin','clamp',\n"
    "  'sealant','adhesive', or NULL. Use this for fastener/material questions instead of ILIKE.\n"
    "- sub_type TEXT (ribs only): 'main' / 'nose' / 'trailing-edge'.\n"
    "- variant TEXT: 'standard' / 'long-range' / NULL. The long-range wing is an ALTERNATE\n"
    "  configuration, NOT extra parts. A physical count of wing structure must scope to ONE\n"
    "  config: add WHERE variant = 'standard' (else stations from both configs double-count).\n"
    "- materials are named by spec/brand, not generic words: adhesives & sealants also read as\n"
    "  codes EC*, LOCTITE*, CONLEY* (e.g. EC2216B/A); part_category already tags them.\n"
    "\n"
    "CHOOSE THE MEASURE BY INTENT (the key decision)\n"
    "- physical count / 'how many ... used' / 'most or least common' / totals ->\n"
    "  SUM(units_per_assy), NOT COUNT(DISTINCT part_number).\n"
    "- 'how many kinds/types/variants/distinct part numbers' -> COUNT(DISTINCT part_number).\n"
    "- physical positions of a structural part (ribs, etc.) -> COUNT(DISTINCT station_num),\n"
    "  scoped to variant='standard', ALWAYS broken down by sub_type and side (never one\n"
    "  lumped number) — use the breakdown pattern below.\n"
    "- 'list all X' / 'which X are used' -> a LISTING: SELECT DISTINCT part_number, description,\n"
    "  units_per_assy, page_number ORDER BY page_number; filter by part_category when it fits,\n"
    "  else match X AND its synonyms/brand codes with OR ILIKE.\n"
    "\n"
    "PATTERNS (adapt the shape to the question; do not copy verbatim)\n"
    "- Ribs PER SIDE, broken down by sub-type, on ONE configuration. The wing is symmetric,\n"
    "  so the number of distinct stations IS the per-side count — do NOT split or add LH/RH:\n"
    "  SELECT sub_type,\n"
    "         COUNT(DISTINCT station_num) AS ribs_per_side,\n"
    "         array_agg(DISTINCT station_num ORDER BY station_num) AS stations,\n"
    "         (array_agg(DISTINCT page_number))[1:3] AS page_number\n"
    "  FROM parts WHERE part_category = 'rib' AND variant = 'standard'\n"
    "  GROUP BY sub_type ORDER BY sub_type\n"
    "- Compare the types within a category by physical usage (e.g. fasteners):\n"
    "  SELECT part_category AS type, SUM(units_per_assy) AS physical_units,\n"
    "         COUNT(DISTINCT part_number) AS distinct_part_numbers,\n"
    "         (array_agg(DISTINCT page_number))[1:3] AS page_number\n"
    "  FROM parts WHERE part_category IN ('screw','rivet','bolt','nut','washer','pin','clamp')\n"
    "  GROUP BY part_category ORDER BY physical_units DESC NULLS LAST\n"
    "\n"
    "GOTCHAS\n"
    "- Prefer part_category over ILIKE on description (it already handles substrings like\n"
    "  'cement' inside 'reinforcement'). Use ILIKE only for attributes not in a typed column.\n"
    "- Always include page_number so the answer can cite it; for grouped queries use\n"
    "  (array_agg(DISTINCT page_number))[1:3] AS page_number.\n"
    "Return ONLY the SQL: a single SELECT, no semicolon, no markdown, no explanation."
)


def generate_sql(query: str, temperature: float = 0.0) -> str:
    sql = _chat(
        _SQL_SYSTEM,
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
    """Execute the SELECT in its own read-only transaction.

    Defensive about the connection's prior state: ``set_session`` cannot run
    inside a transaction, and a preceding read on a shared connection may have
    left one open, so roll that back first. Without this, a lookup-then-aggregate
    sequence on one connection made every SQL candidate raise here and silently
    fall back to the semantic path (an aggregation question answered "no info").
    Always ends the transaction so the connection is left clean for the next use.
    """
    conn.rollback()  # discard any transaction the previous caller left open
    conn.set_session(readonly=True)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            columns = [d[0] for d in cur.description]
            rows = cur.fetchall()
        return columns, rows
    finally:
        conn.rollback()  # close this read txn (even if it aborted) before restoring
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
        "- Structural-position counts (e.g. 'ribs_per_side'): the wing is symmetric, so the "
        "distinct-station count for a sub-type IS the per-side number. Report it directly per "
        "sub-type (e.g. '11 main ribs and 6 trailing-edge ribs per side'); never add LH and RH "
        "columns together, and never sum the sub-types into a bigger 'total per side'.\n"
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
