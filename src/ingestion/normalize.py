"""Deterministic normalization of vision part rows into typed columns.

Classify once at ingest (station_num, side, part_category, sub_type, variant) so
aggregation SQL groups on columns instead of re-deriving them with ILIKE per query.
Pure and deterministic: no LLM, unit-testable.
"""
import re
from typing import Optional

# Takes the first station in a combined 'STA 71.375 & STA 85.625' row.
_STA_RE = re.compile(r"STA\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)

# LH/RH as a standalone token; guards keep it from firing inside a longer word.
_SIDE_RE = re.compile(r"(?:^|[^A-Z])(LH|RH)(?:[^A-Z]|$)")

# Matched by LEFTMOST keyword, since the catalog names the part type first.
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
    """Wing station as a float, collapsing OCR/format variants ('100.00' -> 100.0).

    Prefers the station field; falls back to a 'STA xx.xxx' token in the description.
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
    """Coarse part category (rib, screw, nut, adhesive, ...) or None."""
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
    """Rib structural sub-type: 'main' / 'nose' / 'trailing-edge'. Only meaningful for rib rows."""
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

    Long-range is an ALTERNATE assembly; this column lets a count scope to one config
    instead of double-counting stations across both.
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
