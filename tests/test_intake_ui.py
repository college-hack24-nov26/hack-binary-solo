"""Streamlit AppTest smoke: consent gate, one answer, language switch, decline saves nothing."""
import pytest
from streamlit.testing.v1 import AppTest

from pathlib import Path

from records import store

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def datadir(tmp_path, monkeypatch):
    monkeypatch.setenv("INTAKE_DATA_DIR", str(tmp_path))
    return tmp_path


def page(name):
    return AppTest.from_file(str(ROOT / "intake" / "ui" / f"{name}.py"), default_timeout=20)


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
        at = page(n).run()
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
    at = page("doctor").run()
    assert not at.exception
    assert any("Chest, patient's left" in t.value for t in at.text_area)
    at.radio[0].set_value("hi").run()
    assert any("छाती" in t.value for t in at.text_area) and not at.exception
