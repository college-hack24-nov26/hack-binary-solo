"""Stateful wrapper used by the CLI and the UI. Everything clinical lives in the pure modules;
this adds consent gating, the clock, red-flag evaluation after every answer and record building."""
import secrets
from datetime import datetime
from typing import Any, Callable, Optional

from .conditions import SKIPPED
from .engine import PathResult, longest_path, recompute_path, validate_answer
from .models import Graph
from .redflags import RedFlagRule, Triggered, evaluate_rules


class ConsentRequired(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now().astimezone()


def new_token() -> str:
    return "PT-" + "".join(secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567") for _ in range(6))


class IntakeSession:
    def __init__(self, graph: Graph, rules: list[RedFlagRule], language: str = "en",
                 clock: Callable[[], datetime] = _now, token: Optional[str] = None):
        self.graph, self.rules, self.language, self.clock = graph, rules, language, clock
        self.token = token or new_token()
        self.created_at = clock()
        self.consent_at: Optional[datetime] = None
        self.answers: dict[str, Any] = {}
        self.timeline: list = []
        self.finished_at: Optional[datetime] = None
        self.assigned_doctor: Optional[str] = None     # chosen by the patient after the quiz
        self._res: PathResult = recompute_path(graph, {})
        self.red_flags: list[Triggered] = []

    # -- state
    @property
    def path(self) -> list[str]:
        return self._res.path

    @property
    def pending(self) -> Optional[str]:
        return self._res.pending

    @property
    def consented(self) -> bool:
        return self.answers.get("consent") == "agree"

    @property
    def declined(self) -> bool:
        return self.answers.get("consent") == "decline"

    @property
    def complete(self) -> bool:
        return self.consented and self._res.complete

    # -- actions
    def answer(self, node_id: str, value: Any) -> PathResult:
        node = self.graph.node(node_id)
        if node_id != "consent" and not self.consented:
            raise ConsentRequired("no questions before explicit consent")
        if node_id not in self._res.path:
            raise ValueError(f"{node_id} is not on the current path")
        validate_answer(node, value)
        new = {**self.answers, node_id: value}
        if node_id == "consent" and value == "agree" and self.consent_at is None:
            self.consent_at = self.clock()
        if node_id == "consent" and value != "agree":
            self.consent_at = None
        self._set(new)
        return self._res

    def skip(self, node_id: str) -> PathResult:
        return self.answer(node_id, SKIPPED)

    def _set(self, answers: dict) -> None:
        self._res = recompute_path(self.graph, answers)
        self.answers = self._res.answers      # answers that no longer apply are dropped here
        self.red_flags = evaluate_rules(self.rules, self.answers)

    def previous(self, node_id: str) -> Optional[str]:
        p = self._res.path
        i = p.index(node_id) if node_id in p else len(p)
        return p[i - 1] if i > 0 else None

    def questions_after_basics(self) -> int:
        """Answered or pending questions on the current path after the safety basics."""
        return sum(1 for n in self.path if self.graph.node(n).section in ("complaint", "module", "history"))

    def progress(self) -> tuple[int, int]:
        """(nodes done, estimated total). Total is an upper bound: it assumes the longest remaining route."""
        done = sum(1 for n in self.path if n in self.answers and n != "consent")
        remaining = longest_path(self.graph, self.pending) if self.pending else 0
        return done, done + remaining

    # -- output
    def to_record(self, complete: bool = False, prior=None):
        from records.build import build_record
        now = self.finished_at if complete and self.finished_at else self.clock()
        return build_record(self.graph, self.rules, self.answers, token=self.token, language=self.language,
                            consent_at=self.consent_at, created_at=self.created_at, now=now,
                            complete=complete, timeline=self.timeline, prior=prior, assigned_doctor=self.assigned_doctor)

    def finish(self):
        if not self.complete:
            raise ValueError("intake is not complete")
        self.finished_at = self.clock()
        return self.to_record(complete=True)
