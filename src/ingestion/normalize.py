"""Deterministic normalization of vision part rows into typed columns.

Even the clean vision rows keep structural facts buried in free text: the wing
station as a string ('100.50'), the side inside '-LH', the part category as a
word, the wing configuration in the figure caption. Aggregation used to re-derive
all of this with ILIKE in *every* generated SQL — fragile and repeated, and the
source of the rib over-count (raw station strings '100'/'100.00'/'100.50' counted
as three positions; the long-range wing figure mixed in with the standard one).

We classify once here, at ingest, into columns the SQL can group on directly:
station_num, side, part_category, sub_type, variant. Pure and deterministic (no
LLM, no API cost), so it is unit-testable and the classification is reviewable.
"""
import re
from typing import Optional

# 'STA 23.625', 'STA 100.50', also matches the first station in a combined
# 'STA 71.375 & STA 85.625' row (we take the row's primary station).
_STA_RE = re.compile(r"STA\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)

# LH/RH as a standalone token: '-LH', ' LH ', 'ANGLE-RH'. The guards keep it from
# firing inside a longer word.
_SIDE_RE = re.compile(r"(?:^|[^A-Z])(LH|RH)(?:[^A-Z]|$)")

# Category keywords. We pick the one whose keyword appears LEFTMOST in the
# description, because the catalog names the part type first ('WASHER UNDER NUT'
# is a washer; 'SEALANT-CATALYTIC ... RIVET SEALS' is a sealant). A fixed priority
# order would mis-tag those by a secondary word. '\bNUT\b' does not match
# 'NUTPLATE' (no word boundary inside the word), so nutplate stays distinct.
_CATEGORY_RULES: list[tuple[str, re.Pattern]] = [
    ("rib", re.compile(r"\bRIB\b")),
    ("rivet", re.compile(r"\bRIVET\b")),
    ("screw", re.compile(r"\bSCREW\b")),
    ("bolt", re.compile(r"\bBOLT\b")),
    ("nutplate", re.compile(r"\bNUTPLATE\b")),
    ("nut", re.compile(r"\bNUT\b")),
    ("washer", re.compile(r"\bWASHER\b")),
    ("pin", re.compile(r"\bPIN\b")),
    ("clamp", re.compile(r"\bCLAMP\b")),
    ("sealant", re.compile(r"\bSEALANT\b")),
    ("adhesive", re.compile(r"ADHESIVE|\bCEMENT\b|\bEPOXY\b")),
]


def station_num(station: Optional[str], description: Optional[str] = None) -> Optional[float]:
    """Wing station as a float, collapsing OCR/format variants.

    '100'/'100.00'/'100.50' -> 100.0/100.0/100.5, so COUNT(DISTINCT station_num)
    counts physical positions, not transcription noise. Prefers the extracted
    station field; falls back to a 'STA xx.xxx' token in the description (combined
    ribs carry the station only in the text, with a null station field).
    """
    if station:
        try:
            return float(station)
        except ValueError:
            pass
    if description:
        m = _STA_RE.search(description)
        if m:
            return float(m.group(1))
    return None


def side(description: Optional[str]) -> Optional[str]:
    """'LH' / 'RH' / None, read from the description."""
    if not description:
        return None
    m = _SIDE_RE.search(description.upper())
    return m.group(1) if m else None


def part_category(description: Optional[str]) -> Optional[str]:
    """Coarse part category (rib, screw, nut, adhesive, ...) or None.

    Lets the fastener/material questions group on a column instead of a pile of
    ILIKE branches in the generated SQL.
    """
    if not description:
        return None
    upper = description.upper()
    best_name: Optional[str] = None
    best_pos = len(upper) + 1
    for name, pattern in _CATEGORY_RULES:
        m = pattern.search(upper)
        if m and m.start() < best_pos:
            best_name, best_pos = name, m.start()
    return best_name


def rib_subtype(description: Optional[str]) -> Optional[str]:
    """Rib structural sub-type: 'main' / 'nose' / 'trailing-edge'.

    Only meaningful for rib rows; the caller passes the category in. RealitySearch
    broke the rib count down by exactly these sub-types.
    """
    if not description:
        return None
    upper = description.upper()
    if "TRAILING EDGE" in upper:
        return "trailing-edge"
    if "NOSE" in upper or "LEADING EDGE" in upper:
        return "nose"
    return "main"


def variant(figure: Optional[str]) -> Optional[str]:
    """Wing configuration: 'standard' / 'long-range' / None.

    The catalog lists the long-range wing as an ALTERNATE assembly, not extra
    ribs. Mixing both under `figure ILIKE '%wing%'` double-counted stations (14
    instead of 11). This column lets a structural count scope to one config.
    """
    upper = (figure or "").upper()
    if "WING STRUCTURE" not in upper:
        return None
    return "long-range" if "LONG RANGE" in upper else "standard"


def classify(description: Optional[str], station: Optional[str],
             figure: Optional[str]) -> dict:
    """All typed columns for one part row, derived from its free-text fields."""
    category = part_category(description)
    return {
        "station_num": station_num(station, description),
        "side": side(description),
        "part_category": category,
        "sub_type": rib_subtype(description) if category == "rib" else None,
        "variant": variant(figure),
    }
