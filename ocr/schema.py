"""Schemas. RawExtraction is what the VLM must return (also sent as the `format` JSON schema).
The final result adds code-computed fields (structured frequency, formulary match, needsReview)."""
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

DocType = Literal["prescription", "lab_report", "discharge_summary", "other"]


class RawMedication(BaseModel):
    model_config = ConfigDict(extra="ignore")
    nameAsWritten: str
    strength: Optional[str] = None
    form: Optional[str] = None
    route: Optional[str] = None
    frequencyAsWritten: Optional[str] = None
    durationAsWritten: Optional[str] = None
    notes: Optional[str] = None
    confidence: float = Field(ge=0, le=1)


class RawLab(BaseModel):
    model_config = ConfigDict(extra="ignore")
    test: str
    value: Optional[str] = None
    unit: Optional[str] = None
    referenceRange: Optional[str] = None
    flag: Optional[str] = None
    confidence: float = Field(ge=0, le=1)


class RawExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    documentType: DocType
    documentDate: Optional[str] = None
    medications: list[RawMedication] = []
    labResults: list[RawLab] = []
    diagnosesAsWritten: list[str] = []
    unreadable: list[str] = []
    warnings: list[str] = []


def vlm_json_schema() -> dict:
    """JSON schema for Ollama's `format`. Every property is marked required: with optional
    properties the model tends to skip them and return empty lists (observed with qwen3-vl).
    Nullable fields stay nullable, so "unreadable" -> null still works."""
    schema = RawExtraction.model_json_schema()
    for node in [schema, *schema.get("$defs", {}).values()]:
        node["required"] = list(node["properties"].keys())
    return schema
