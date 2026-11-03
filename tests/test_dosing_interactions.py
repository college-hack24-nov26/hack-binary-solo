"""Interactions: current medicines (free text), same-visit drugs, duplicate class, severities from the data."""
from dosing_helpers import F, quiz, run, texts


def has(items, needle):
    return any(needle.lower() in t.lower() for t in texts(items))


def test_duplicate_nsaids_in_the_same_visit_block_with_the_formulary_severity():
    row = next(r for r in F().interactions if r["a"] == "class:NSAID" and r["b"] == "class:NSAID")
    res = run("ibuprofen", "pain/fever", quiz(), selected_rule_id="ibuprofen#0", visit_drugs=["diclofenac"])
    dup = [i for i in res["interactions"] if i["kind"] == "duplicate"]
    assert dup and dup[0]["severity"] == row["severity"]
    assert res["status"] == "blocked" and has(res["blocks"], "diclofenac")


def test_duplicate_from_current_medicine_brand_name():
    res = run("ibuprofen", "pain/fever", quiz(meds_any="yes", meds_list="Voveran"), selected_rule_id="ibuprofen#0")
    assert any(i["kind"] == "duplicate" for i in res["interactions"])


def test_nsaid_plus_arb_from_free_text_is_a_major_warning():
    row = next(r for r in F().interactions if r["a"] == "class:NSAID" and "ARB" in r["b"])
    res = run("ibuprofen", "pain/fever", quiz(meds_any="yes", meds_list="Telma 40"), selected_rule_id="ibuprofen#0")
    it = [i for i in res["interactions"] if i["severity"] == row["severity"]]
    assert it and row["action"] in it[0]["action"]


def test_metronidazole_plus_warfarin_generic_and_brand():
    row = next(r for r in F().interactions if r["a"] == "metronidazole" and r["b"] == "warfarin")
    for txt in ("warfarin", "Coumadin 5 mg"):
        res = run("metronidazole", "amoebiasis", quiz(meds_any="yes", meds_list=txt, hx_abdomen=["none"]))
        it = [i for i in res["interactions"] if row["action"] in i["action"]]
        assert it and it[0]["severity"] == row["severity"], txt


def test_unrecognised_token_is_surfaced_and_unspecified_severity_is_kept():
    res = run("azithromycin", "Campylobacter", quiz(meds_any="yes", meds_list="warfarin, Zorbitex"))
    assert has(res["warnings"], "unparsed: doctor to review: 'Zorbitex'")
    assert any(i["severity"] == "unspecified" for i in res["interactions"])


def test_herbal_word_is_recognised_but_flagged():
    res = run("paracetamol", "pain/fever", quiz(meds_any="yes", meds_list="giloy kadha"), selected_rule_id="paracetamol#0")
    assert has(res["warnings"], "herbal")


def test_contraindicated_interaction_blocks():
    res = run("ciprofloxacin", "cystitis", quiz(meds_any="yes", meds_list="tizanidine"), selected_rule_id="ciprofloxacin#1")
    assert res["status"] == "blocked" and has(res["blocks"], "tizanidine")


def test_qt_flag_between_visit_drugs():
    res = run("ondansetron", "gastroenteritis vomiting", quiz(age_y=4, wt=12), visit_drugs=["azithromycin"], doctor_inputs={"qt_history": "no"})
    assert any("qt" in i["with"].lower() or i["with"].startswith("azithromycin") for i in res["interactions"])
