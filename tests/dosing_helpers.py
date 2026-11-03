"""Shared builders for the dosing tests. Expected values in the tests are derived from the formulary JSON."""
import json

from dosing import config, engine, formulary, mapper

CFG = config.Config(allow_unverified=False)
CFG_UNVERIFIED = config.Config(allow_unverified=True)


def F():
    return formulary.load(CFG.formulary_path)


def quiz(age_y=40, age_m=None, sex="male", wt=70, **over):
    """A complete answer set for the basics. Pass key=None to drop a node (not asked)."""
    a = {"consent": "agree", "age_years": age_y, "sex": sex, "weight_kg": wt, "allergies": ["none"], "meds_any": "no",
         "kidney": "no", "liver": "no", "diabetes": "no", "hypertension": "no", "asthma": "no",
         "chief_complaint": "fever", "danger_signs": ["none"]}
    if age_y == 0:
        a["age_months"] = age_m if age_m is not None else 0
    a.update(over)
    return {k: v for k, v in a.items() if v is not None}


def run(drug, ind, answers=None, cfg=None, **kw):
    ctx = mapper.map_quiz(answers if answers is not None else quiz())
    return engine.evaluate(engine.Request(drug, ctx, ind, **kw), cfg or CFG)


def texts(items):
    return [x["text"] if isinstance(x, dict) else x for x in items]


def rules_of(drug_id):
    return F().drugs[drug_id]["dose_rules"]


def rid_for(drug_id, indication_label, **match):
    """Index of the first rule with this exact indication (and any extra field values)."""
    for i, r in enumerate(rules_of(drug_id)):
        if r["indication"] == indication_label and all(r.get(k) == v for k, v in match.items()):
            return f"{drug_id}#{i}"
    raise KeyError(indication_label)


def dump(res):
    return json.dumps(res, sort_keys=True)
