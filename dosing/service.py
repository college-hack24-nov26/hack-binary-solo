"""Glue between a PatientRecord, the engine and the audit log. The UI calls these; tests call them too."""
import json
from datetime import datetime
from typing import Optional

from records.schema import DosingCheck, PatientRecord

from . import audit
from .config import Config
from .engine import Request, evaluate
from .mapper import map_record


def evaluate_for_record(rec: PatientRecord, drug: str, indication: Optional[str], *, doctor_id: str, doctor_inputs: Optional[dict] = None,
                        confirmed: Optional[list] = None, visit_drugs: Optional[list] = None, selected_rule_id: Optional[str] = None,
                        form: Optional[str] = None, route: Optional[str] = None, show_all_rules: bool = False,
                        override_reason: Optional[str] = None, cfg: Optional[Config] = None, now: Optional[datetime] = None,
                        log: bool = True) -> dict:
    cfg = cfg or Config.from_env()
    req = Request(drug=drug, context=map_record(rec), indication=indication, doctor_inputs=dict(doctor_inputs or {}),
                  confirmed=list(confirmed or []), visit_drugs=list(visit_drugs or []), selected_rule_id=selected_rule_id,
                  form=form, route=route, show_all_rules=show_all_rules, override_reason=override_reason, doctor_id=doctor_id)
    res = evaluate(req, cfg)
    if log:
        inputs = {"doctor_inputs": req.doctor_inputs, "confirmed": req.confirmed, "visit_drugs": req.visit_drugs,
                  "selected_rule_id": selected_rule_id, "form": form, "route": route, "show_all_rules": show_all_rules}
        audit.write("evaluate", token=rec.token, doctor_id=doctor_id, drug=res.get("drug") or drug, result=res, inputs=inputs,
                    provenance=res["provenance"], override_reason=override_reason, now=now)
        for o in res["overrides"]:
            audit.write("override", token=rec.token, doctor_id=doctor_id, drug=res.get("drug") or drug, result=res, inputs=inputs,
                        provenance=res["provenance"], override_reason=o["reason"], now=now, extra={"overridden_block": o["block"]})
    return res


def can_confirm(res: dict) -> bool:
    """Only a complete, final result can be saved to the record."""
    return res.get("status") == "ok" and bool(res.get("final")) and not res.get("needs_input")


def confirm(rec: PatientRecord, res: dict, *, doctor_id: str, doctor_inputs: Optional[dict] = None, now: Optional[datetime] = None,
            cfg: Optional[Config] = None) -> PatientRecord:
    """Append a DosingCheck to the record (quiz answers are never modified) and write the audit entry."""
    if not can_confirm(res):
        raise ValueError("result is not final: cannot confirm")
    now = now or datetime.now().astimezone()
    chk = DosingCheck(at=now.isoformat(timespec="seconds"), doctorId=doctor_id, drug=res["drug"], indication=res["indication"],
                      ruleId=res["selected_rule_id"], status=res["status"], dataStatus=res["data_status"],
                      result=json.loads(json.dumps(res)), doctorInputs=dict(doctor_inputs or {}),
                      overrideReasons=[o["reason"] for o in res["overrides"]])
    audit.write("confirm", token=rec.token, doctor_id=doctor_id, drug=res["drug"], result=res,
                inputs={"doctor_inputs": dict(doctor_inputs or {})}, provenance=res["provenance"], now=now,
                override_reason="; ".join(chk.overrideReasons) or None)
    return rec.model_copy(update={"dosingChecks": rec.dosingChecks + [chk]})
