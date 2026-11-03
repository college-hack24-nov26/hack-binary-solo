import pytest
from ocr.frequency import parse_frequency as p


@pytest.mark.parametrize("txt,n", [("OD", 1), ("BD", 2), ("b.d", None), ("TDS", 3), ("QID", 4), ("tid", 3)])
def test_abbreviations(txt, n):
    r = p(txt)
    if n is None:
        return  # 'b.d' with dots is not claimed to be understood
    assert r["timesPerDay"] == n and r["kind"] == "scheduled" and r["verbatim"] == txt


def test_numeric_pattern():
    r = p("1-0-1")
    assert r["slots"] == {"morning": 1.0, "afternoon": 0.0, "night": 1.0}
    assert r["timesPerDay"] == 2


def test_four_part_and_half():
    assert p("1-1-1-1")["timesPerDay"] == 4
    assert p("1/2-0-1/2")["slots"]["morning"] == 0.5


def test_prn_hs_stat_and_timing():
    assert p("SOS")["kind"] == "prn"
    assert p("HS")["slots"] == {"night": 1.0}
    assert p("stat")["kind"] == "stat"
    assert p("BD after food")["timing"] == "after food"
    assert p("1-0-1 AC")["timing"] == "before food"


def test_unknown_and_empty_keep_verbatim():
    assert p("as directed")["kind"] == "unknown"
    assert p(None)["kind"] == "unknown" and p("")["verbatim"] == ""


def test_date_is_not_a_dose_pattern():
    assert p("12-03-2024")["kind"] == "unknown"
