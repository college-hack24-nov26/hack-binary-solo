"""Pydantic models for data/intake_graph.json."""
import json
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

from .conditions import check_condition

ROOT = Path(__file__).resolve().parent.parent
GRAPH_PATH = ROOT / "data" / "intake_graph.json"
LANGS = ("en", "hi", "mr")
END = "END"
TRANSLATION_STATUS = "machine-drafted, needs native review"

NodeType = Literal["single_choice", "multi_choice", "number", "scale_0_10", "yes_no_unsure", "free_text", "body_map"]
Section = Literal["consent", "basics", "complaint", "module", "history"]
Socrates = Literal["site", "onset", "character", "radiation", "associated",
                   "time_course", "exacerbating_relieving", "severity"]


class Text(BaseModel):
    model_config = ConfigDict(extra="forbid")
    en: str
    hi: str
    mr: str

    def get(self, lang: str) -> str:
        return getattr(self, lang if lang in LANGS else "en") or self.en


class Option(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    en: str
    hi: str
    mr: str

    def get(self, lang: str) -> str:
        return getattr(self, lang if lang in LANGS else "en") or self.en


class Rule(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    if_: dict = Field(alias="if")
    goto: str

    @field_validator("if_")
    @classmethod
    def _cond(cls, v):
        check_condition(v)
        return v


class Next(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rules: list[Rule] = []
    default: str


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    type: NodeType
    section: Section
    text: Text
    options: list[Option] = []
    next: Next
    socrates: Optional[Socrates] = None
    shortLabel: Optional[str] = None      # English label for the doctor summary
    maxSelections: Optional[int] = None   # body_map only
    min: Optional[float] = None
    max: Optional[float] = None
    redFlagRefs: list[str] = []
    translationStatus: str = TRANSLATION_STATUS

    @model_validator(mode="after")
    def _shape(self):
        ids = [o.id for o in self.options]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{self.id}: duplicate option ids")
        if self.type in ("single_choice", "multi_choice", "yes_no_unsure") and not ids:
            raise ValueError(f"{self.id}: {self.type} needs options")
        if self.type == "body_map":
            if not self.maxSelections or self.maxSelections < 1:
                raise ValueError(f"{self.id}: body_map needs maxSelections >= 1")
            if not {"unsure", "tell_doctor"} <= set(ids) or not set(ids) <= {"unsure", "tell_doctor", "none"}:
                raise ValueError(f"{self.id}: body_map options must include unsure and tell_doctor (and may add none)")
        elif self.maxSelections is not None:
            raise ValueError(f"{self.id}: maxSelections only applies to body_map")
        if self.type not in ("single_choice", "multi_choice", "yes_no_unsure", "body_map") and ids:
            raise ValueError(f"{self.id}: {self.type} must not have options")
        if self.type == "yes_no_unsure" and ids != ["yes", "no", "unsure"]:
            raise ValueError(f"{self.id}: yes_no_unsure options must be yes, no, unsure")
        if self.type == "number" and (self.min is None or self.max is None):
            raise ValueError(f"{self.id}: number needs min and max")
        return self

    def option(self, oid: str) -> Optional[Option]:
        return next((o for o in self.options if o.id == oid), None)


class Graph(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    start: str
    nodes: list[Node]

    _index: dict[str, Node] = PrivateAttr(default_factory=dict)

    def model_post_init(self, _ctx) -> None:
        self._index = {n.id: n for n in self.nodes}

    def node(self, nid: str) -> Node:
        return self._index[nid]

    def ids(self) -> list[str]:
        return [n.id for n in self.nodes]


def load_graph(path: Path | str = GRAPH_PATH) -> Graph:
    return Graph.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
