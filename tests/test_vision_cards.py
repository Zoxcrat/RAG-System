"""Unit tests for the clean per-part chunks fed into the documents table."""
from src.ingestion.vision_parts import _card_text, is_real_part_number


def test_is_real_part_number_rejects_cross_reference_placeholders():
    # 'SEE FIG N' rows point to another figure; they are not catalog parts.
    assert is_real_part_number("0523010-1") is True
    assert is_real_part_number("LOCTITE 872L") is True
    assert is_real_part_number("SEE FIG 11") is False
    assert is_real_part_number("SEE FIGURE 30") is False
    assert is_real_part_number("") is False
    assert is_real_part_number(None) is False


def test_card_text_includes_part_number_description_and_context():
    text = _card_text(
        {
            "part_number": "0512017-1",
            "description": "SHELF-RADIO",
            "station": None,
            "units_per_assy": 1,
        },
        figure="Fuselage Aft Section Assembly",
    )
    assert "0512017-1" in text
    assert "SHELF-RADIO" in text
    assert "Section: Fuselage Aft Section Assembly" in text
    assert "1 per assembly" in text


def test_card_text_adds_wing_station_when_present():
    text = _card_text(
        {
            "part_number": "0523010-1",
            "description": "RIB ASSEMBLY-LH",
            "station": "23.625",
            "units_per_assy": 2,
        },
        figure="Wing Structure Assembly",
    )
    assert "wing station 23.625" in text


def test_card_text_handles_missing_optional_fields():
    text = _card_text(
        {"part_number": "AN3-5", "description": None, "station": None,
         "units_per_assy": None},
        figure=None,
    )
    # Falls back to just the part number, no dangling separators or 'None'.
    assert text.strip() == "Part AN3-5."
    assert "None" not in text
