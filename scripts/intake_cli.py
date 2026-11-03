"""Terminal simulator for the question flow (no UI). Type an option number, a value, 's' skip,
'?' not sure, 'b' back. Red flags print as they trigger."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intake.conditions import UNSURE  # noqa: E402
from intake.engine import answer_label  # noqa: E402
from intake.models import load_graph  # noqa: E402
from intake.redflags import load_rules  # noqa: E402
from intake.session import IntakeSession  # noqa: E402
from intake.summary import render_text, build_summary  # noqa: E402


def main(lang: str = "en") -> None:
    g, rules = load_graph(), load_rules()
    s = IntakeSession(g, rules, language=lang)
    seen: set[str] = set()
    view = s.pending
    while True:
        view = view or s.pending
        if view is None:
            break
        n = g.node(view)
        print(f"\n[{s.progress()[0]}/{s.progress()[1]}] {n.text.get(lang)}")
        for i, o in enumerate(n.options, 1):
            print(f"  {i}. {o.get(lang)}")
        if n.type == "multi_choice":
            print("  (comma-separated numbers)")
        if view in s.answers:
            print(f"  current: {answer_label(n, s.answers[view], lang)}")
        raw = input("> ").strip()
        try:
            if raw == "b":
                view = s.previous(view)
                continue
            if raw == "s" and view != "consent":
                s.skip(view)
            elif raw == "?" and view != "consent":
                s.answer(view, [UNSURE] if n.type == "multi_choice" else UNSURE)
            elif n.type == "multi_choice":
                s.answer(view, [n.options[int(x) - 1].id for x in raw.split(",")])
            elif n.options:
                s.answer(view, n.options[int(raw) - 1].id)
            elif n.type in ("number", "scale_0_10"):
                s.answer(view, float(raw) if "." in raw else int(raw))
            else:
                s.answer(view, raw)
        except (ValueError, IndexError, KeyError) as e:
            print("  !", e)
            continue
        view = None
        for t in s.red_flags:
            if t.ruleId not in seen:
                seen.add(t.ruleId)
                print(f"  *** RED FLAG {t.ruleId}: {t.staffMessage} ({t.label})")
        if s.declined:
            print("Consent declined. No questions asked.")
            return
    rec = s.finish()
    print("\n" + render_text(build_summary(rec)))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "en")
