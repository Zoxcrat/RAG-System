"""Parse OCR'd catalog text into structured part rows for aggregation queries."""
import re
from typing import Optional, TypedDict

# Part-number token + UPPERCASE description. Numbers are Cessna-style (digits +
# optional suffix) or standard hardware, e.g. 0512029-8, NAS680A3, AN960-4.
_PART_RE = re.compile(
    r"^([0-9]{6,7}-?[0-9]{0,3}|[A-Z]{1,4}[0-9]{2,}[A-Z0-9-]*)\s+([A-Z][A-Z0-9 ./~&\-]{3,})"
)

# Figure captions give each part a section context ("Wing Structure Assembly").
_FIG_RE = re.compile(r"Figure\s+(\d+[A-Z]?)\.?\s+(.+)", re.IGNORECASE)


class PartRecord(TypedDict):
    part_number: str
    description: str
    page_number: int
    figure: Optional[str]


def _clean(text: str) -> str:
    """Trim trailing OCR dashes/tildes/dots and collapse whitespace."""
    return re.sub(r"\s+", " ", text).strip(" -~.—")


def extract_parts(pages: list[dict]) -> list[PartRecord]:
    """Parse OCR'd pages into part rows; each part inherits the figure above it."""
    records: list[PartRecord] = []
    current_figure: Optional[str] = None

    for page in pages:
        page_number = page["page_number"]
        for line in page["text"].splitlines():
            stripped = line.strip()

            fig = _FIG_RE.search(stripped)
            if fig:
                current_figure = _clean(fig.group(2))[:80] or None
                continue

            match = _PART_RE.match(stripped)
            if match:
                description = _clean(match.group(2))
                if description:
                    records.append(
                        {
                            "part_number": match.group(1),
                            "description": description,
                            "page_number": page_number,
                            "figure": current_figure,
                        }
                    )

    return records


def ingest_parts(conn, pages: list[dict]) -> int:
    """Rebuild the `parts` table from OCR'd pages. Returns the row count."""
    from psycopg2.extras import execute_values

    records = extract_parts(pages)
    rows = [
        (r["part_number"], r["description"], r["page_number"], r["figure"])
        for r in records
    ]
    with conn.cursor() as cur:
        cur.execute("TRUNCATE parts RESTART IDENTITY;")
        if rows:
            execute_values(
                cur,
                "INSERT INTO parts (part_number, description, page_number, figure) VALUES %s",
                rows,
            )
    conn.commit()
    return len(rows)


if __name__ == "__main__":
    import sys

    from src.db import get_connection, init_schema
    from src.pdf_loader import load_extracted_text

    json_path = sys.argv[1] if len(sys.argv) > 1 else "data/cessna_172_ocr.json"
    conn = get_connection()
    try:
        init_schema(conn)
        n = ingest_parts(conn, load_extracted_text(json_path))
        print(f"Extracted and stored {n} parts from {json_path}")
    finally:
        conn.close()
