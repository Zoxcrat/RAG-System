"""Tests for structured parts extraction (pure, no DB)."""
from src.ingestion.parts import extract_parts


def test_extracts_part_number_description_and_page():
    pages = [{
        "page_number": 5,
        "text": "0512029-8 STRINGER ASSEMBLY-AFT CABIN TOP RH\nNAS680A3 NUTPLATE",
    }]
    recs = extract_parts(pages)

    assert recs[0]["part_number"] == "0512029-8"
    assert recs[0]["description"] == "STRINGER ASSEMBLY-AFT CABIN TOP RH"
    assert recs[0]["page_number"] == 5
    assert recs[1]["part_number"] == "NAS680A3"
    assert recs[1]["description"] == "NUTPLATE"


def test_figure_caption_becomes_section_for_following_parts():
    pages = [{
        "page_number": 101,
        "text": "Figure 26. Wing Structure Assembly\n0523010-1 RIB ASSEMBLY-LH STA 23.625",
    }]
    recs = extract_parts(pages)

    assert recs[0]["figure"] == "Wing Structure Assembly"


def test_ignores_headers_and_noise():
    pages = [{
        "page_number": 1,
        "text": "MODEL 172 & P172\nillustrated parts catalog\n172 SERIAL 17249545",
    }]
    assert extract_parts(pages) == []
