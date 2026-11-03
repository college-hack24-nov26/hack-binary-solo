"""Validate data/intake_graph.json (and cross-check data/red_flags.json). Exit 1 on any problem."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intake.engine import longest_path, validate_graph  # noqa: E402
from intake.models import load_graph  # noqa: E402
from intake.redflags import load_rules  # noqa: E402


def main() -> int:
    graph = load_graph()
    rules = load_rules()
    errs = validate_graph(graph, {r.id for r in rules})
    for e in errs:
        print("ERROR", e)
    if not errs:
        print(f"OK: {len(graph.nodes)} nodes, {len(rules)} red-flag rules; "
              f"longest route after safety basics: {longest_path(graph, 'chief_complaint')} questions")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
