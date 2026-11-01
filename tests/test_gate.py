"""Receipt gate rules (lexicon/rules/GATE_RULES.md). Needs DUTYDROP_DATA_DIR with ch99.txt."""
import datetime as dt
import os

import pytest

from dutydrop import data as D, gate

pytestmark = pytest.mark.skipif(not os.path.exists(os.path.join(os.environ.get("DUTYDROP_DATA_DIR", ""), "ch99.txt")),
                                reason="needs HTS data")
TODAY = dt.date(2026, 10, 31)


@pytest.fixture(scope="module")
def d():
    return D.load()


def heads(r):
    return [l.get("heading") for l in r["line_items"][1:]]


def test_mug_china_stacks_301_forced_labor(d):
    r = gate.firm_receipt(d, "6912.00.44.00", "China", 100, unit_price=1, today=TODAY)
    assert r["total"] == "22.50" and heads(r) == ["9903.05.31"]


def test_saucepan_one_metals_heading_no_forced_labor(d):
    r = gate.firm_receipt(d, "7323.93.00.45", "Vietnam", 100, unit_price=1, today=TODAY)
    assert heads(r) == ["9903.82.09"] and r["total"] == "27.00"


def test_heater_15pct_floor_with_weight_scenario(d):
    r = gate.firm_receipt(d, "8516.29.00.30", "Vietnam", 100, unit_price=1, today=TODAY)
    assert heads(r) == ["9903.82.10"] and r["total"] == "15.00"
    assert any("15% of weight" in s["label"] for s in r["scenarios"])


def test_hammer_on_no_note16_list(d):
    r = gate.firm_receipt(d, "8205.20.30.00", "Mexico", 100, unit_price=1, today=TODAY)
    assert not any(h.startswith("9903.82") for h in heads(r))
    assert any(s["label"] == "If USMCA qualifying" for s in r["scenarios"])


def test_aquarium_not_quartz_and_no_2019_transit_heading(d):
    r = gate.firm_receipt(d, "7020.00.60.00", "China", 100, unit_price=1, today=TODAY)
    assert r["total"] is not None
    assert "9903.88.09" not in heads(r) and "9903.45.30" not in heads(r)


def test_battery_drops_end_use_and_unlisted_headings(d):
    r = gate.firm_receipt(d, "8507.60.00.90", "China", 100, unit_price=1, today=TODAY)
    assert "9903.94.07" not in heads(r) and "9903.91.08" not in heads(r)
    assert "9903.91.06" in heads(r)


def test_note52b_listed_article_owes_no_country_duty(d):
    r = gate.firm_receipt(d, "8471.60.20.00", "Vietnam", 100, unit_price=1, today=TODAY)
    assert r["total"] == "0.00"
    assert not any(h.startswith("9903.05") for h in heads(r))


def test_note_list_parser_reads_note52(d):
    assert "84716020" in gate.note_list_codes(52, "b")
