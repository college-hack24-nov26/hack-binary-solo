"""Doctor-only Dosage check. Thin wrapper over dosing.service: results go out exactly as the engine made them, wrapped as
{result, card}. Confirm never trusts a client-sent result: it uses the server's cached evaluation (or re-evaluates)."""
import json
import secrets
import threading
import time
from collections import OrderedDict
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request

from dosing import history as hist, meds, service
from dosing.config import BANNER, DEMO_BANNER, OVERRIDE_CATEGORIES
from dosing.engine import apply_inputs
from dosing.mapper import map_record
from dosing.rules import indications
from records import store

from ..deps import WRITE_LOCK, User, doctor_only, dosing_formulary
from ..result_card import ELSEWHERE, card_model, choice_options, field_kind, override_error
from ..schemas import ConfirmIn, Confirmed, Drugs, EvaluateIn, Evaluation, HistoryIn, HistoryItems, HistoryItemsIn, HistoryOut
from .patients import load_or_404

router = APIRouter(tags=["dosing"])

# patient-context grid of the Streamlit panel (dosing_panel.SHOW)
SHOW = [("weight_kg", "Weight (kg)"), ("age_months", "Age (months)"), ("sex", "Sex"), ("pregnant", "Pregnant"),
        ("allergy_penicillins", "Penicillin allergy"), ("allergy_nsaids", "NSAID allergy"), ("kidney_disease", "Kidney disease"),
        ("liver_disease", "Liver disease"), ("diabetes", "Diabetes"), ("hypertension", "Hypertension"), ("asthma", "Asthma"),
        ("ulcer", "Ulcer"), ("alcohol", "Alcohol"), ("heart_disease", "Heart disease")]


class ResultCache:
    """Evaluations by id, so Confirm uses exactly what the server computed. Bounded and time-limited."""

    def __init__(self, max_items: int = 500, ttl_s: int = 3600):
        self._d: OrderedDict[str, dict] = OrderedDict()
        self._lock = threading.Lock()
        self.max_items, self.ttl_s = max_items, ttl_s

    def put(self, entry: dict) -> str:
        rid = secrets.token_urlsafe(12)
        with self._lock:
            self._d[rid] = {**entry, "at": time.time()}
            while len(self._d) > self.max_items:
                self._d.popitem(last=False)
        return rid

    def get(self, rid: str) -> dict | None:
        with self._lock:
            e = self._d.get(rid)
            if e is None or time.time() - e["at"] > self.ttl_s:
                self._d.pop(rid, None)
                return None
            return e

    def drop(self, rid: str) -> None:
        with self._lock:
            self._d.pop(rid, None)


def card(res: dict) -> dict:
    m = card_model(res)
    missing = []
    for n in m["missing"]:
        kind, key = field_kind(n["field"])
        missing.append({**n, "kind": kind, "key": key, "options": choice_options(n["field"]) if kind == "choice" else
                        (["yes", "no", "unsure"] if kind == "tri" else []),
                        "hint": ELSEWHERE.get(key, "Enter this in the doctor-entered inputs above.") if kind == "elsewhere" else None})
    return {**m, "missing": missing}


@lru_cache(maxsize=1)
def _brands() -> dict[str, list[str]]:
    """Brand names per drug id, from the synonym table (engine-side mapping, not formulary content; pharmacist review pending)."""
    out: dict[str, list[str]] = {}
    for e in json.loads(meds.DATA.read_text(encoding="utf-8"))["entries"]:
        if e.get("drug_id") and e.get("kind") == "generic":
            generic = {meds.canon(n) for n in (e["generic"], e["drug_id"].replace("_", " "))}
            out[e["drug_id"]] = [n for n in e["names"] if meds.canon(n) not in generic]
    return out


@router.get("/api/dosing/drugs", response_model=Drugs, dependencies=[Depends(doctor_only)])
def drugs(fc=Depends(dosing_formulary)):
    f, cfg = fc
    out = []
    brands = _brands()
    for did, d in f.drugs.items():
        forms = [f"{x.get('form')} {x.get('strength')}".strip() for x in d.get("forms_india") or [] if x.get("form")]
        out.append({"id": did, "generic": d["generic"], "indications": [{"key": i["key"], "labels": i["labels"]} for i in indications(d)],
                    "forms": list(dict.fromkeys(forms)), "brands": brands.get(did, [])})
    return {"drugs": out, "overrideCategories": OVERRIDE_CATEGORIES, "banner": BANNER, "demoBanner": DEMO_BANNER,
            "allowUnverified": cfg.allow_unverified, "demoMode": cfg.demo_mode}


@router.post("/api/dosing/history-items", response_model=HistoryItems, dependencies=[Depends(doctor_only)])
def history_items(body: HistoryItemsIn, fc=Depends(dosing_formulary)):
    f, _ = fc
    if body.drug not in f.drugs:
        raise HTTPException(422, "Unknown drug.")
    rec = load_or_404(body.token)
    ctx = map_record(rec)
    ctx2 = apply_inputs(ctx, {}, [], rec.visitHistory)
    items = hist.items_for(f, f.drugs[body.drug], ctx2)
    todo = hist.unknown_items(items)
    context = []
    for name, label in SHOW:
        v = ctx2.f.get(name)
        context.append({"name": name, "label": label, "value": None if v is None or v.value is None else str(v.value),
                        "provenance": ctx2.prov(name)})

    def tag(o):
        return ("from scanned prescription" + (f" ({o['scan_date']})" if o.get("scan_date") else "")) \
            if o["source"] == "ocr_doctor_confirmed" else "patient-reported"
    meds = []
    for m in ctx2.all_meds():
        origins = [{"source": m.source, "scan_date": m.scan_date}] + list(m.also)
        meds.append({"generic": m.generic, "raw": m.raw, "sources": list(dict.fromkeys(tag(o) for o in origins))})
    return {"items": [i.as_dict() for i in items], "unknown": [i.as_dict() for i in todo], "context": context, "medicines": meds,
            "unparsed": list(ctx2.unparsed_meds), "ocrUnparsed": list(ctx2.ocr_unparsed)}


@router.post("/api/patients/{token}/history", response_model=HistoryOut)
def save_history(token: str, body: HistoryIn, request: Request, user: User = Depends(doctor_only)):
    if not body.answers:
        raise HTTPException(422, "Nothing answered yet.")
    with WRITE_LOCK:
        rec = load_or_404(token)
        try:
            rec = service.save_history(rec, dict(body.answers), doctor_id=user.username)
        except ValueError as e:
            raise HTTPException(422, str(e))
        store.save(rec)
    request.app.state.events.publish("patient.updated", {"token": token})
    return {"visitHistory": rec.visitHistory, "by": rec.visitHistoryBy, "at": rec.visitHistoryAt}


def _evaluate(body: EvaluateIn, user: User) -> tuple[dict, dict]:
    """Caller holds WRITE_LOCK (evaluate writes the audit log). Returns (record-free cache entry, result)."""
    if body.overrideReason is not None or body.overrideCategory is not None:
        err = override_error(body.overrideCategory, body.overrideReason)
        if err:
            raise HTTPException(422, err)
    rec = load_or_404(body.token)
    try:
        res = service.evaluate_for_record(
            rec, body.drug, body.indication, doctor_id=user.username, doctor_inputs=body.doctorInputs, confirmed=body.confirmed,
            visit_drugs=body.visitDrugs, selected_rule_id=body.selectedRuleId, form=body.form, route=body.route,
            show_all_rules=body.showAllRules, override_reason=body.overrideReason.strip() if body.overrideReason else None,
            override_category=body.overrideCategory)
    except ValueError as e:                    # e.g. a doctor input of the wrong kind; the engine names the field
        raise HTTPException(422, str(e))
    return {"token": body.token, "doctorInputs": dict(body.doctorInputs), "result": res, "doctor": user.username}, res


@router.post("/api/dosing/evaluate", response_model=Evaluation)
def evaluate(body: EvaluateIn, request: Request, user: User = Depends(doctor_only), _fc=Depends(dosing_formulary)):
    with WRITE_LOCK:
        entry, res = _evaluate(body, user)
    rid = request.app.state.results.put(entry)
    return {"resultId": rid, "result": res, "card": card(res), "canConfirm": service.can_confirm(res, False),
            "canConfirmIfAcknowledged": service.can_confirm(res, True)}


@router.post("/api/dosing/confirm", response_model=Confirmed)
def confirm(body: ConfirmIn, request: Request, user: User = Depends(doctor_only), _fc=Depends(dosing_formulary)):
    cache: ResultCache = request.app.state.results
    with WRITE_LOCK:
        if body.resultId:
            entry = cache.get(body.resultId)
            if entry is None:
                raise HTTPException(409, "This result is no longer available. Run the dosage check again.")
            if entry["token"] != body.token or entry["doctor"] != user.username:
                raise HTTPException(409, "This result belongs to another patient or doctor. Run the dosage check again.")
        elif body.request is not None:
            if body.request.token != body.token:
                raise HTTPException(422, "The request is for another patient.")
            entry, _ = _evaluate(body.request, user)
        else:
            raise HTTPException(422, "Send the resultId of the check to confirm.")
        res = entry["result"]
        if not service.can_confirm(res, body.acknowledged):
            raise HTTPException(409, "This result cannot be confirmed: it is not final, or the unchecked items are not ticked.")
        rec = service.confirm(load_or_404(body.token), res, doctor_id=user.username, doctor_inputs=entry["doctorInputs"],
                              acknowledged=body.acknowledged)
        store.save(rec)
        if body.resultId:
            cache.drop(body.resultId)
    request.app.state.events.publish("patient.updated", {"token": body.token})
    return {"dosingChecks": [c.model_dump() for c in rec.dosingChecks]}

