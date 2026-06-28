"""Vision-LLM extraction of the structured `parts` table.

Flat OCR linearizes the IPC's 2-D table and destroys the UNITS-PER-ASSY and
USABLE-ON columns (dotted leaders become noise). This module renders each page
and asks a vision model to return full rows as JSON, recovering the columns
aggregation needs. Runs through the Batch API (50% cheaper) and caches per page,
so a re-run only processes pages not already done (idempotent and resumable).
"""
import base64
import json
import os
import re
import time
from typing import Optional

import anthropic
import fitz  # PyMuPDF
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

MODEL = "claude-sonnet-4-6"  # matches Opus quality on this scan at 1/2 the cost
LONG_EDGE = 2200             # keep batch payload small; JPEG q85 stays legible
JPEG_QUALITY = 85
MAX_TOKENS = 8000
PAGES_PER_BATCH = 150        # stay well under the 256 MB / batch submission cap
POLL_SECONDS = 20

DEFAULT_PDF = "data/Cessna 172 Parts Catalog (1963-1974).pdf"
DEFAULT_CACHE = "data/cessna_172_parts_vision.json"
DEFAULT_OCR = "data/cessna_172_ocr.json"
# Source tag for the structured chunks fed into the `documents` retrieval table,
# kept distinct from the flat-OCR source so the two representations never collide
# on content_hash and stay individually traceable.
CARDS_SOURCE = "cessna_172_parts_vision"

SYSTEM = (
    "You extract rows from a scanned Cessna Illustrated Parts Catalog (IPC) page. "
    "Columns: FIGURE/INDEX NO, PART NUMBER, DESCRIPTION, UNITS PER ASSY, USABLE-ON CODE. "
    "Dotted leaders (......) connect the description to the units column. "
    "Return ONLY a JSON object (no markdown) with key 'rows': a list of objects with keys "
    "index_no (string or null), part_number, description, units_per_assy (integer or null), "
    "usable_on (string or null), station (wing station like '23.625' if the description "
    "contains 'STA xx.xxx', else null). "
    "Transcribe part numbers EXACTLY as printed: letters O/I/L and digits 0/1 occur in real "
    "combinations; never 'correct' a trailing L into 1 or vice-versa. "
    "Reconstruct each row under scan noise; an unreadable value -> null. Never invent part "
    "numbers. If the page is not a parts list (intro text, illustration only), return "
    '{"rows": []}.'
)

_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def render_jpeg_b64(pdf_path: str, page_number: int) -> str:
    """Render a 1-based page to a base64 JPEG, long edge clamped to LONG_EDGE.

    JPEG (not PNG) keeps the Batch API submission well under its size cap while
    staying legible for the small part-number digits.
    """
    with fitz.open(pdf_path) as doc:
        page = doc[page_number - 1]
        zoom = LONG_EDGE / max(page.rect.width, page.rect.height)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))  # alpha=False by default
        data = pix.tobytes(output="jpg", jpg_quality=JPEG_QUALITY)
    return base64.b64encode(data).decode()


# 'SEE FIG 11' rows are cross-references — the part is enumerated in another
# figure, not here. They carry no real part number, unit or category, so in the
# parts table they would corrupt 'list all' and COUNT(DISTINCT part_number).
_PLACEHOLDER_PN_RE = re.compile(r"^\s*SEE\b", re.IGNORECASE)


def is_real_part_number(pn: Optional[str]) -> bool:
    """False for empty values and cross-reference placeholders ('SEE FIG 11')."""
    pn = (pn or "").strip()
    return bool(pn) and not _PLACEHOLDER_PN_RE.match(pn)


def _parse_rows(text: str) -> list[dict]:
    text = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
    rows = json.loads(text).get("rows", [])
    # Drop header bleed / junk: a row is only useful with a real part number.
    return [r for r in rows if is_real_part_number(r.get("part_number"))]


def _page_count(pdf_path: str) -> int:
    with fitz.open(pdf_path) as doc:
        return doc.page_count


def load_cache(path: str) -> dict:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)


def _request_for(pdf_path: str, page_number: int) -> Request:
    img = render_jpeg_b64(pdf_path, page_number)
    return Request(
        custom_id=f"page-{page_number}",
        params=MessageCreateParamsNonStreaming(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64",
                                                 "media_type": "image/jpeg", "data": img}},
                    {"type": "text", "text": f"Extract every parts-list row on page {page_number}."},
                ],
            }],
        ),
    )


def _run_one_batch(pages: list[int], pdf_path: str, cache: dict, cache_path: str) -> None:
    client = _get_client()
    print(f"  building {len(pages)} requests (pages {pages[0]}..{pages[-1]})...")
    requests = [_request_for(pdf_path, p) for p in pages]
    batch = client.messages.batches.create(requests=requests)
    print(f"  batch {batch.id} submitted; polling...")

    while True:
        b = client.messages.batches.retrieve(batch.id)
        if b.processing_status == "ended":
            break
        time.sleep(POLL_SECONDS)

    done = errored = 0
    for result in client.messages.batches.results(batch.id):
        page = int(result.custom_id.split("-")[1])
        if result.result.type == "succeeded":
            msg = result.result.message
            try:
                text = next(blk.text for blk in msg.content if blk.type == "text")
                cache[str(page)] = {"rows": _parse_rows(text)}
                done += 1
            except (StopIteration, json.JSONDecodeError):
                errored += 1
        else:
            errored += 1
    save_cache(cache, cache_path)
    print(f"  stored {done} pages, {errored} errored, cache now {len(cache)} pages")


def run(pdf_path: str = DEFAULT_PDF, cache_path: str = DEFAULT_CACHE,
        max_pages: Optional[int] = None) -> dict:
    """Extract all pages not already cached. Idempotent and resumable."""
    total = _page_count(pdf_path)
    if max_pages:
        total = min(total, max_pages)
    cache = load_cache(cache_path)
    pending = [p for p in range(1, total + 1) if str(p) not in cache]
    print(f"{len(cache)} pages cached, {len(pending)}/{total} pending")

    for i in range(0, len(pending), PAGES_PER_BATCH):
        chunk = pending[i:i + PAGES_PER_BATCH]
        _run_one_batch(chunk, pdf_path, cache, cache_path)
    return cache


_FIG_RE = re.compile(r"Figure\s+(\d+[A-Z]?)\.?\s+(.+)", re.IGNORECASE)


def page_figure_map(ocr_path: str) -> dict[int, str]:
    """Map page_number -> figure/section caption, carried forward from OCR.

    The vision rows carry no figure caption (the model returns table rows, not
    headings); the OCR text has the readable 'Figure N. <caption>' headers. We
    scan pages in order and assign each page the most recent caption, giving the
    parts table a section column for scoping ('wing', 'fuselage', ...).
    """
    with open(ocr_path, encoding="utf-8") as f:
        pages = json.load(f)
    mapping: dict[int, str] = {}
    current = None
    for p in sorted(pages, key=lambda x: x["page_number"]):
        for line in p["text"].splitlines():
            m = _FIG_RE.search(line.strip())
            if m:
                current = re.sub(r"\s+", " ", m.group(2)).strip(" -~.—")[:80] or current
        if current:
            mapping[p["page_number"]] = current
    return mapping


def _card_text(row: dict, figure: Optional[str]) -> str:
    """A clean, self-contained sentence describing one catalog part.

    Flat OCR stores this line mangled and interleaved with its neighbours
    ('0512017-1 SHELF-RADIO' buried between 'NUTPLATE —' and 'ATTACHING PARTS'),
    so its embedding never matches a natural-language part query. Rebuilt from the
    vision row, the chunk carries the part number, description and its section
    context together (contextual retrieval), which is what the lookup path needs.
    """
    pn = (row.get("part_number") or "").strip()
    desc = (row.get("description") or "").strip()
    head = f"Part {pn}: {desc}" if desc else f"Part {pn}"
    bits: list[str] = []
    if figure:
        bits.append(f"Section: {figure}")
    if row.get("station"):
        bits.append(f"wing station {row['station']}")
    qty = row.get("units_per_assy")
    if isinstance(qty, int):
        bits.append(f"{qty} per assembly")
    return f"{head}. " + (", ".join(bits) + "." if bits else "")


def ingest_part_cards(conn, cache_path: str = DEFAULT_CACHE,
                      ocr_path: str = DEFAULT_OCR) -> int:
    """Add clean per-part chunks (from the vision rows) to the `documents` table.

    Additive to the flat-OCR chunks, not a replacement: OCR keeps the running
    prose (intro notes, narrative) that a parts row has no equivalent for, while
    these cards give the semantic path a noise-free representation of every part
    line. Reuses the ingest store (batch embed + content_hash dedup), so it is
    idempotent. Returns the number of new chunks inserted.
    """
    from src.ingestion.ingest import _store_records

    cache = load_cache(cache_path)
    fig_map = page_figure_map(ocr_path) if os.path.exists(ocr_path) else {}
    records = []
    for page_str, payload in cache.items():
        page = int(page_str)
        figure = fig_map.get(page)
        for r in payload.get("rows", []):
            if not is_real_part_number(r.get("part_number")):
                continue
            records.append((_card_text(r, figure), CARDS_SOURCE, len(records), page))
    return _store_records(conn, records)


def ingest_parts_from_vision(conn, cache_path: str = DEFAULT_CACHE,
                             ocr_path: str = DEFAULT_OCR) -> int:
    """Rebuild the `parts` table from the cached vision rows. Returns row count.

    Derives the typed columns (station_num, side, part_category, sub_type, variant)
    from each row's free text at load time (see src/ingestion/normalize.py), so the
    aggregation SQL groups on clean columns instead of re-deriving them per query.
    """
    from psycopg2.extras import execute_values

    from src.ingestion.normalize import classify

    cache = load_cache(cache_path)
    fig_map = page_figure_map(ocr_path) if os.path.exists(ocr_path) else {}
    rows = []
    for page_str, payload in cache.items():
        page = int(page_str)
        figure = fig_map.get(page)
        for r in payload.get("rows", []):
            if not is_real_part_number(r.get("part_number")):
                continue
            pn = r.get("part_number").strip()
            qty = r.get("units_per_assy")
            description = (r.get("description") or "").strip() or None
            station = r.get("station") or None
            typed = classify(description, station, figure)
            rows.append((
                pn,
                description,
                page,
                figure,  # section caption carried forward from OCR (page_figure_map)
                qty if isinstance(qty, int) else None,
                (r.get("usable_on") or None),
                station,
                (r.get("index_no") or None),
                typed["station_num"],
                typed["side"],
                typed["part_category"],
                typed["sub_type"],
                typed["variant"],
            ))
    with conn.cursor() as cur:
        cur.execute("TRUNCATE parts RESTART IDENTITY;")
        if rows:
            execute_values(
                cur,
                "INSERT INTO parts (part_number, description, page_number, figure, "
                "units_per_assy, usable_on, station, index_no, "
                "station_num, side, part_category, sub_type, variant) VALUES %s",
                rows,
            )
    conn.commit()
    return len(rows)


if __name__ == "__main__":
    import sys

    mp = int(sys.argv[1]) if len(sys.argv) > 1 else None
    run(max_pages=mp)
