"""Optional, off by default. A short paragraph from a LOCAL Ollama model, labelled AI-drafted.
The model sees only a number-free fact sheet, and its output is rejected (template used instead) if
it contains digits, dose/drug-instruction words or diagnostic language. Never called unless the
doctor asks for it."""
import os
import re
from dataclasses import dataclass

import requests

from ocr.config import load_settings        # enforces localhost-only OLLAMA_URL

from .summary import Summary, template_paragraph

LABEL = "AI-drafted - check against the structured fields"
_BAN = re.compile(r"\d|\b(mg|mcg|ml|iu|tablets?|tabs?|capsules?|doses?|dosage|daily|twice|thrice|bd|tds|od|qid|"
                  r"diagnos\w*|likely|probabl\w*|suggest\w*|consistent with|rule out|treat\w*|prescrib\w*|recommend\w*)\b",
                  re.I)
SYSTEM = ("You rewrite structured patient-intake facts into 3 to 5 plain sentences for a doctor. "
          "Use only the facts given. Do not write any numbers, doses, drug names, diagnoses, causes, "
          "or advice. Do not add facts. If something is marked missing, say it is missing.")


@dataclass
class ParagraphResult:
    text: str
    source: str        # "ai-drafted" | "template"
    reason: str = ""


def _digits_to_words(severity_text: str) -> str:
    m = re.search(r"(\d+)/10", severity_text)
    if not m:
        return severity_text
    n = int(m.group(1))
    return re.sub(r"\d+/10", "mild" if n <= 3 else "moderate" if n <= 6 else "severe", severity_text)


def fact_sheet(s: Summary) -> str:
    """Number-free facts: complaint, SOCRATES, history, allergy classes, and which items are missing."""
    lines = []
    for sec in s.sections:
        for f in sec.fields:
            if f.key == "complaint.main" or f.key.startswith(("socrates.", "history.")):
                lines.append(f"{f.label}: {_digits_to_words(f.value)}")
            elif f.missing:
                lines.append(f"Missing information: {f.label}")
    lines.append("Red flags were triggered; they are listed separately." if any(
        f.key.startswith("redFlag.") and f.key != "redFlag.none" for sec in s.sections for f in sec.fields)
        else "No red flags were triggered.")
    return "\n".join(re.sub(r"\d+", "", l) for l in lines)


def draft_paragraph(s: Summary, enabled: bool = False, model: str | None = None, timeout: int = 60) -> ParagraphResult:
    fallback = lambda why: ParagraphResult(template_paragraph(s), "template", why)
    if not enabled:
        return fallback("AI paragraph is off")
    cfg = load_settings()
    model = model or os.environ.get("INTAKE_LLM_MODEL", "qwen3:8b")
    body = {"model": model, "stream": False, "think": False, "keep_alive": cfg.keep_alive,
            "options": {"temperature": 0},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": fact_sheet(s)}]}
    try:
        r = requests.post(f"{cfg.ollama_url}/api/chat", json=body, timeout=timeout)
        r.raise_for_status()
        text = r.json()["message"]["content"].strip()
    except Exception as e:  # noqa: BLE001
        return fallback(f"Ollama unavailable ({type(e).__name__})")
    if not text:
        return fallback("empty model output")
    if (bad := _BAN.search(text)):
        return fallback(f"model output rejected (contained {bad.group(0)!r})")
    return ParagraphResult(text, "ai-drafted")
