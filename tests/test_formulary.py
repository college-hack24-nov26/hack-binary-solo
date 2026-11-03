from ocr.formulary import match_drug, normalize


def test_exact_and_prefix_strength_stripped():
    assert normalize("Tab. Paracetamol 500 mg") == "paracetamol"
    r = match_drug("Tab. Metformin 500mg")
    assert r["suggestedGeneric"] == "metformin" and r["matchScore"] == 1.0


def test_typo_suggests_but_does_not_rewrite():
    r = match_drug("Paracetmol")
    assert r["suggestedGeneric"] == "paracetamol" and 0.85 <= r["matchScore"] < 1


def test_unknown_drug_has_no_suggestion():
    assert match_drug("Zorbitex")["suggestedGeneric"] is None
    assert match_drug("")["suggestedGeneric"] is None


def test_alias():
    assert match_drug("Amoxiclav")["suggestedGeneric"] == "amoxicillin-clavulanate"


def test_similar_names_not_confused():
    assert match_drug("Metoprolol")["suggestedGeneric"] != "metformin"
