"""Streamlit AppTest smoke: consent gate, one answer, language switch, decline saves nothing."""
import time

import pytest
from streamlit.testing.v1 import AppTest

from pathlib import Path

from records import store

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def datadir(tmp_path, monkeypatch):
    monkeypatch.setenv("INTAKE_DATA_DIR", str(tmp_path))
    return tmp_path


def page(name, role=None):
    at = AppTest.from_file(str(ROOT / "intake" / "ui" / f"{name}.py"), default_timeout=20)
    if role:  # staff / doctor pages need a login; the kiosk does not
        at.session_state["auth"] = {"username": f"test_{role}", "role": role, "last_seen": time.time()}
    return at


def test_patient_flow_consent_then_question_and_language():
    at = page("patient").run()
    assert not at.exception
    assert [b.label for b in at.button][:2] == ["I agree", "I do not agree"]      # no question before consent
    at.button(key="consent_agree").click().run()
    assert "age" in at.header[0].value.lower()
    at.radio[0].set_value("hi").run()
    assert "उम्र" in at.header[0].value
    assert [r.token for r in store.list_records()] and store.list_records()[0].consent.given


def test_decline_saves_nothing():
    at = page("patient").run()
    at.button(key="consent_decline").click().run()
    assert not at.exception and store.list_records() == []
    assert "No questions were asked" in at.info[0].value


def test_staff_and_doctor_pages_render_empty():
    for n in ("staff", "doctor"):
        at = page(n, "doctor").run()
        assert not at.exception, n


# ------------------------------------------------------------ body map page (list fallback; the tap component
# itself is checked in a real browser, see README)
def at_site(node="cp_site", cc="chest_pain"):
    from intake.models import load_graph
    from intake.redflags import load_rules
    from intake.synthetic import run_bank
    s = run_bank(load_graph(), load_rules(), {"chief_complaint": cc}, stop_at=node, allow_unused=True)
    at = page("patient")
    at.session_state["sess"], at.session_state["stage"], at.session_state["view"] = s, "flow", None
    return at.run(), s


def test_body_map_question_renders_with_list_and_special_options():
    at, s = at_site()
    assert not at.exception and "pain" in at.header[0].value.lower()
    labels = [b.label for b in at.button]
    assert "I'm not sure" in labels and "I'd prefer to tell the doctor" in labels
    assert at.checkbox(key="bm_cb_cp_site_chest_left").label == "Chest, patient's left"
    assert at.button(key="bm_next_cp_site").disabled                    # nothing selected yet


def test_list_selection_stores_canonical_answer_and_advances():
    from intake.bodymap import make_answer
    at, s = at_site()
    at.checkbox(key="bm_cb_cp_site_chest_left").check().run()
    at.checkbox(key="bm_cb_cp_site_chest_center").check().run()
    at.button(key="bm_next_cp_site").click().run()
    assert s.answers["cp_site"] == make_answer(["chest_center", "chest_left"], "list")
    assert s.pending == "cp_onset"


def test_list_enforces_max_selections():
    at, s = at_site()                                                    # cp_site allows 3
    for rid in ("chest_left", "chest_center", "chest_right", "upper_abdomen_left"):
        at.checkbox(key=f"bm_cb_cp_site_{rid}").check().run()
    at.button(key="bm_next_cp_site").click().run()
    assert len(s.answers["cp_site"]["regions"]) == 3 and "upper_abdomen_left" not in s.answers["cp_site"]["regions"]


def test_not_sure_and_tell_doctor_options():
    at, s = at_site()
    at.button(key="bm_opt_unsure_cp_site").click().run()
    assert s.answers["cp_site"] == "unsure"
    at, s = at_site("hd_site", "headache")
    at.button(key="bm_opt_tell_doctor_hd_site").click().run()
    assert s.answers["hd_site"]["special"] == "tell_doctor" and s.answers["hd_site"]["regions"] == []


def test_hindi_labels_on_the_list():
    at, _ = at_site()
    at.radio[0].set_value("hi").run()
    assert "छाती" in at.checkbox(key="bm_cb_cp_site_chest_left").label


def test_back_then_revisit_shows_stored_selection():
    from intake.bodymap import make_answer
    at, s = at_site()
    at.checkbox(key="bm_cb_cp_site_chest_left").check().run()
    at.button(key="bm_next_cp_site").click().run()
    at.button(key="back").click().run()                                  # back to cp_site
    assert at.checkbox(key="bm_cb_cp_site_chest_left").value is True
    at.checkbox(key="bm_cb_cp_site_chest_left").uncheck().run()          # remove the selection ...
    assert at.button(key="bm_next_cp_site").disabled                     # ... Next is blocked until something is chosen


def test_doctor_page_shows_regions_and_diagram(tmp_path):
    from intake.bodymap import make_answer
    from intake.models import load_graph
    from intake.redflags import load_rules
    from intake.synthetic import run_bank
    r = run_bank(load_graph(), load_rules(), {"chief_complaint": "chest_pain", "cp_site": make_answer(["chest_left"], "list")},
                 token="PT-DOCAAA").finish()
    store.save(r)
    at = page("doctor", "doctor").run()
    assert not at.exception
    assert any("Chest, patient's left" in t.value for t in at.text_area)
    at.radio[0].set_value("hi").run()
    assert any("छाती" in t.value for t in at.text_area) and not at.exception


# ------------------------------------------------------------ demo mode
def test_demo_button_loads_chest_pain_patient_to_review_and_saves_record():
    at = page("patient").run()
    at.button(key="demo_mode").click().run()
    assert not at.exception
    assert "Synthetic demo patient" in at.info[0].value
    assert at.button(key="chg_cp_site")                                  # review screen lists the body-map question
    recs = store.list_records()
    assert len(recs) == 1 and recs[0].complaint.id == "chest_pain" and recs[0].status == "in_progress"
    assert [f.ruleId for f in recs[0].redFlags] == ["RF_CHEST_PAIN_RADIATION_SWEATING"]


def test_demo_flow_finishes_and_hindi_strings_exist():
    at = page("patient").run()
    at.radio[0].set_value("hi").run()
    assert "डेमो" in at.button(key="demo_mode").label
    at.button(key="demo_mode").click().run()
    assert "डेमो" in at.info[0].value
    next(b for b in at.button if "पूरा करें" in b.label).click().run()    # finish
    assert not at.exception
    assert store.list_records()[0].status == "complete"


def test_demo_button_not_offered_after_consent():
    at, _ = at_site()
    assert "demo_mode" not in [b.key for b in at.button]


def test_demo_mode_is_idempotent_one_record_on_the_staff_board():
    from intake.demo import DEMO_TOKEN
    for _ in range(3):                                                   # three clicks, from fresh kiosks
        at = page("patient").run()
        at.button(key="demo_mode").click().run()
        assert not at.exception
    recs = store.list_records()
    assert [r.token for r in recs] == [DEMO_TOKEN] and recs[0].status == "in_progress"
    # a finished demo, then another click: still one record, reset to in_progress
    next(b for b in at.button if "finish" in b.label.lower()).click().run()
    assert store.load(DEMO_TOKEN).status == "complete"
    at = page("patient").run()
    at.button(key="demo_mode").click().run()
    assert [r.token for r in store.list_records()] == [DEMO_TOKEN] and store.load(DEMO_TOKEN).status == "in_progress"
    staff = page("staff", "staff").run()
    assert len(staff.expander) == 1
