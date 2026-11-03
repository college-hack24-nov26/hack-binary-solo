"""Drive a session from a dict of scripted answers (tests, smoke script)."""
from typing import Any, Callable, Optional

from .models import Graph
from .redflags import RedFlagRule
from .session import IntakeSession


def run_script(graph: Graph, rules: list[RedFlagRule], script: dict[str, Any], *, language: str = "en",
               clock: Optional[Callable] = None, token: Optional[str] = None, strict: bool = True) -> IntakeSession:
    """Answer each pending node from `script`. strict: fail if a pending node has no scripted answer
    or the script has answers that were never asked (so stale scripts are caught)."""
    kw = {"clock": clock} if clock else {}
    s = IntakeSession(graph, rules, language=language, token=token, **kw)
    used = set()
    while s.pending:
        nid = s.pending
        if nid not in script:
            if strict:
                raise KeyError(f"script has no answer for {nid}")
            break
        s.answer(nid, script[nid])
        used.add(nid)
    unused = set(script) - used
    if strict and unused:
        raise KeyError(f"scripted answers never asked: {sorted(unused)}")
    return s
