"""Rule-based red flags: deterministic, no model involved. Rules live in data/red_flags.json and
are DRAFTS until a clinician fills `source` and sets sourceChecked=true."""
import json
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator

from .conditions import check_condition, evaluate, is_answered, referenced_nodes
from .models import ROOT, TRANSLATION_STATUS, Text

RULES_PATH = ROOT / "data" / "red_flags.json"
DRAFT_LABEL = "Draft rule, source check pending"
REVIEW_STATUS = "draft - clinician review pending"


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    section: str
    url: str
    accessedOn: str


class PatientMessage(Text):
    translationStatus: str = TRANSLATION_STATUS

    model_config = ConfigDict(extra="forbid")


class RedFlagRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    condition: dict
    severity: Literal["urgent", "soon"]
    staffMessage: str
    patientMessage: PatientMessage
    source: Optional[Source] = None
    sourceChecked: bool = False
    reviewStatus: str = REVIEW_STATUS

    @field_validator("condition")
    @classmethod
    def _cond(cls, v):
        check_condition(v)
        return v

    @property
    def is_draft(self) -> bool:
        return not (self.sourceChecked and self.source is not None)


class Triggered(BaseModel):
    ruleId: str
    severity: str
    staffMessage: str
    patientMessage: dict
    draft: bool
    label: str                       # "Draft rule, source check pending" or the source name
    triggeredBy: dict                # node id -> answer, for every node the rule reads that has an answer


def load_rules(path: Path | str = RULES_PATH) -> list[RedFlagRule]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rules = [RedFlagRule.model_validate(r) for r in raw["rules"]]
    ids = [r.id for r in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate red flag rule ids")
    return rules


def evaluate_rules(rules: list[RedFlagRule], answers: dict) -> list[Triggered]:
    """Fired rules, urgent before soon, file order within a severity."""
    out = []
    for r in rules:
        if evaluate(r.condition, answers):
            out.append(Triggered(
                ruleId=r.id, severity=r.severity, staffMessage=r.staffMessage,
                patientMessage=r.patientMessage.model_dump(), draft=r.is_draft,
                label=DRAFT_LABEL if r.is_draft else f"{r.source.name}, {r.source.section}",
                triggeredBy={n: answers[n] for n in referenced_nodes(r.condition) if is_answered(answers, n)}))
    return sorted(out, key=lambda t: t.severity != "urgent")
