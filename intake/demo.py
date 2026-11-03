"""Demo mode: one fully synthetic chest-pain patient, pre-filled so the whole flow can be shown in about 90 seconds.
Answers come from intake.synthetic.PATIENTS (no real data). Red flags are still produced by the normal rules."""
from typing import Optional

from .models import Graph
from .redflags import RedFlagRule
from .session import IntakeSession
from .synthetic import PATIENTS, run_bank

DEMO_SCENARIO = "adult_chest_pain"


def load_demo(graph: Graph, rules: list[RedFlagRule], language: str = "en", token: Optional[str] = None) -> IntakeSession:
    """A session that has answered every question on the chest-pain path (consent included) and is ready for review."""
    s = run_bank(graph, rules, PATIENTS[DEMO_SCENARIO], language=language, token=token)
    assert s.complete
    return s
