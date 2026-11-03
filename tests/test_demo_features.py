"""Demo features: fixtures through the dosing service, Load demo patient, result-card paths, audit viewer, reset script."""
import json
import time
from datetime import date
from pathlib import Path

import pytest

from dosing import audit, audit_view, demo, service
from api import result_card
from records import store

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def datadir(tmp_path, monkeypatch):
    monkeypatch.setenv("INTAKE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DEMO_MODE", raising=False)
    return tmp_path


# ------------------------------------------------------------------ fixtures through the service
@pytest.mark.parametrize("key", list(demo.DEMO_PATIENTS))
def test_each_fixture_runs_with_designed_status_and_writes_audit(key):
    n0 = len(audit.read())
    runs = demo.run_fixture(key)
    assert [res["status"] for _, res in runs] == [r["expect_status"] for r, _ in runs]
    new = audit.read()[n0:]
    assert new and all(e["token"] == demo.DEMO_PATIENTS[key]["token"] for e in new)
    assert sum(e["event"] == "evaluate" for e in new if e["event"] != "history") >= len(runs)
    assert audit.verify()


def test_fixtures_are_obviously_synthetic_and_cover_three_paths():
    fx = demo.DEMO_PATIENTS
    assert [f["displayName"] for f in fx.values()] == ["Demo Patient A", "Demo Patient B", "Demo Patient C"]
    assert all(f["synthetic"] for f in fx.values())
    expected = {s for f in fx.values() for r in f["runs"] for s in [r["expect_status"]]}
    assert {"ok", "needs_input", "blocked"} <= expected
    assert fx["penicillin_allergy"]["runs"][-1]["override_category"] and len(fx["penicillin_allergy"]["runs"][-1]["override_reason"]) >= 10


def test_blocked_fixture_has_no_dose_until_override_is_recorded():
    runs = demo.run_fixture("penicillin_allergy")
    for _, res in runs[:2]:
        assert res["status"] == "blocked" and res["dose_mg"] is None and res["product"] is None and res["daily_total_mg"] is None
    last = runs[-1][1]
    assert last["status"] == "ok" and last["dose_mg"] and last["overrides"][0]["category"] == "benefit_outweighs_risk"
    assert [e["event"] for e in audit.read() if e["event"] == "override"]


# ------------------------------------------------------------------ result card model
def test_card_headers_and_reasons_per_status():
    by = {}
    for key in demo.DEMO_PATIENTS:
        for _, res in demo.run_fixture(key):
            by.setdefault(res["status"], res)
    assert result_card.card_model(by["ok"])["header"] == "Dose ready for doctor review"
    nm = result_card.card_model(by["needs_input"])
    assert nm["header"] == "More information needed" and "scr_mg_dl" in nm["responsible"] and nm["missing"]
    bm = result_card.card_model(by["blocked"])
    assert bm["header"] == "Blocked: safety rule" and bm["reason"].startswith("Contraindication") and bm["sources"] and not bm["show_numbers"]
    assert all(s["id"] for s in bm["sources"][:1])
    refused = demo.service.evaluate_for_record(demo.record("child_fever"), "warfarinol", "x", doctor_id="d", cfg=demo.DEMO_CFG)
    rm = result_card.card_model(refused)
    assert refused["status"] == "refused" and rm["header"] == "Refused: no data for this case" and not rm["show_numbers"] and rm["reason"]


def test_override_requires_category_and_ten_characters():
    assert result_card.override_error("", "long enough reason") and result_card.override_error("other", "short")
    assert result_card.override_error("other", "  short   ") and result_card.override_error("bogus", "long enough reason")
    assert result_card.override_error("other", "long enough reason") is None


def test_needs_input_fields_map_to_inputs():
    assert result_card.field_kind("scr_mg_dl") == ("num", "scr_mg_dl")
    assert result_card.field_kind("qt_history")[0] == "tri" and result_card.field_kind("q_abc123")[0] == "tri"
    assert result_card.field_kind("pregnant")[0] == "choice" and result_card.field_kind("meds_text")[0] == "text"
    assert result_card.field_kind("selected_rule_id")[0] == "rule"
    assert result_card.field_kind("age_exact") == ("num", "age_exact_days")






def dose_metrics(at):
    return [m for m in at.metric if m.label == "Dose"]


def card_text(at):
    return " ".join(x.value for coll in (at.error, at.success, at.info, at.warning, at.markdown) for x in coll)








# ------------------------------------------------------------------ audit viewer
def seeded_log():
    for key in demo.DEMO_PATIENTS:
        demo.run_fixture(key)
    return audit.read()


def test_audit_rows_filters_and_exports():
    entries = seeded_log()
    rs = audit_view.rows(entries)
    assert [r["time"] for r in rs] == sorted((r["time"] for r in rs), reverse=True)
    assert {r["action"] for r in rs} >= {"evaluated", "override", "history-check answered"}
    only = audit_view.filter_rows(rs, patient="PT-DEMOC2", action="override")
    assert only and all(r["patient"] == "PT-DEMOC2" and r["action"] == "override" for r in only)
    assert audit_view.filter_rows(rs, drug="metformin") and not audit_view.filter_rows(rs, start=date(2999, 1, 1))
    assert audit_view.filter_rows(rs, start=date(2000, 1, 1), end=date(2999, 1, 1)) == rs
    js = json.loads(audit_view.to_json(only))
    assert js == [r["entry"] for r in only] and js[0]["override_reason"]
    csv_lines = audit_view.to_csv(only).splitlines()
    assert csv_lines[0].startswith("time,doctor,patient,drug,status,action") and len(csv_lines) == len(only) + 1
    d = audit_view.detail(only[0]["entry"])
    assert d["override_category"] == "benefit_outweighs_risk" and d["calculation_steps"] and d["sources"] and d["inputs"]


def test_tampering_with_one_line_is_detected():
    seeded_log()
    assert audit.verify()
    p = audit.log_path()
    lines = p.read_text(encoding="utf-8").splitlines()
    e = json.loads(lines[2])
    e["status"] = "ok" if e["status"] != "ok" else "blocked"
    lines[2] = json.dumps(e, sort_keys=True, ensure_ascii=False)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert not audit.verify()


def test_deleting_a_line_is_detected():
    seeded_log()
    p = audit.log_path()
    lines = p.read_text(encoding="utf-8").splitlines()
    p.write_text("\n".join(lines[:1] + lines[2:]) + "\n", encoding="utf-8")
    assert not audit.verify()


# ------------------------------------------------------------------ reset script
def test_reset_demo_data_clears_demo_records_and_audit_but_not_other_patients(datadir):
    import importlib.util
    spec = importlib.util.spec_from_file_location("reset_demo_data", ROOT / "scripts" / "reset_demo_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    seeded_log()
    for k in demo.DEMO_PATIENTS:
        store.save(demo.record(k))
    other = demo.record("child_fever").model_copy(update={"token": "PT-ABCDEF"})
    store.save(other)
    r = mod.reset()
    assert sorted(r["records_removed"]) == sorted(p["token"] for p in demo.DEMO_PATIENTS.values())
    assert store.load("PT-ABCDEF") is not None and all(store.load(p["token"]) is None for p in demo.DEMO_PATIENTS.values())
    assert audit.read() == [] and audit.verify()
    # a log shared with another patient is left alone unless asked
    seeded_log()
    service.evaluate_for_record(other, "paracetamol", "pain/fever", doctor_id="d", cfg=demo.DEMO_CFG)
    n = len(audit.read())
    r = mod.reset()
    assert len(audit.read()) == n and "--rechain-others" in r["audit_note"]
    r = mod.reset(rechain_others=True)
    left = audit.read()
    assert left and all(e["token"] == "PT-ABCDEF" for e in left) and audit.verify()
