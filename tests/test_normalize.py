"""Unit tests for the deterministic part-row normalization (typed columns)."""
from src.ingestion import normalize


def test_station_num_collapses_format_variants():
    # The bug behind the rib over-count: these three are one physical position.
    assert normalize.station_num("100") == 100.0
    assert normalize.station_num("100.00") == 100.0
    assert normalize.station_num("100.50") == 100.5


def test_station_num_falls_back_to_description_token():
    # Combined ribs carry the station only in the text, with a null station field.
    assert normalize.station_num(None, "RIB-STA 118") == 118.0
    assert normalize.station_num(None, "RIB ASSEMBLY-TRAILING EDGE STA 71.375") == 71.375


def test_station_num_none_when_absent():
    assert normalize.station_num(None, "NUTPLATE UPPER") is None
    assert normalize.station_num("", None) is None


def test_side_reads_lh_rh_as_standalone_token():
    assert normalize.side("RIB ASSEMBLY-LH STA 23.625") == "LH"
    assert normalize.side("0523230-1 ANGLE-RH") == "RH"
    assert normalize.side("BRACKET LH WING") == "LH"
    assert normalize.side("NUTPLATE UPPER") is None


def test_part_category_specificity():
    assert normalize.part_category("RIB ASSEMBLY-LH STA 23.625") == "rib"
    assert normalize.part_category("SCREW") == "screw"
    assert normalize.part_category("NAS680A08 NUTPLATE") == "nutplate"  # not 'nut'
    assert normalize.part_category("NAS395-14-3 NUT") == "nut"
    assert normalize.part_category("EC2216B/A ADHESIVE METAL TO METAL") == "adhesive"
    assert normalize.part_category("576.1 SEALANT-EXTRUDED") == "sealant"
    assert normalize.part_category("1024A-3 CEMENT PARTS A & B") == "adhesive"
    assert normalize.part_category("GROMMET") is None


def test_part_category_does_not_match_cement_inside_reinforcement():
    assert normalize.part_category("0523023-1 REINFORCEMENT") is None


def test_part_category_uses_leading_noun_not_a_secondary_word():
    # The part type is the first word; a secondary mention must not win.
    assert normalize.part_category("WASHER UNDER NUT") == "washer"
    assert normalize.part_category(
        "SEALANT-CATALYTIC. GENERAL PURPOSE FOR FILLET & RIVET SEALS"
    ) == "sealant"


def test_rib_subtype():
    assert normalize.rib_subtype("RIB-TRAILING EDGE STA 57.125") == "trailing-edge"
    assert normalize.rib_subtype("RIB ASSEMBLY-NOSE STA 40.375") == "nose"
    assert normalize.rib_subtype("RIB-LH STA 154") == "main"


def test_variant_separates_standard_from_long_range():
    assert normalize.variant("Wing Structure Assembly") == "standard"
    assert normalize.variant("Wing Structure Assembly - Long Range") == "long-range"
    assert normalize.variant("Fuel System Installation") is None
    assert normalize.variant(None) is None


def test_classify_bundles_all_columns_for_a_main_rib():
    out = normalize.classify(
        "0523010-1 RIB ASSEMBLY-LH STA 23.625", "23.625", "Wing Structure Assembly"
    )
    assert out == {
        "station_num": 23.625,
        "side": "LH",
        "part_category": "rib",
        "sub_type": "main",
        "variant": "standard",
    }


def test_classify_sub_type_only_for_ribs():
    out = normalize.classify("SCREW", None, "Wing Structure Assembly")
    assert out["part_category"] == "screw"
    assert out["sub_type"] is None
