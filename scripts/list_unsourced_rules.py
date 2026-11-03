"""List every red-flag rule that has no source (or an unchecked one). Exit 1 if any remain."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intake.redflags import load_rules  # noqa: E402


def main() -> int:
    rules = load_rules()
    todo = [r for r in rules if r.source is None or not r.sourceChecked]
    for r in todo:
        why = "no source" if r.source is None else "source not checked"
        print(f"{r.id:40s} {r.severity:7s} {why:18s} {r.reviewStatus}")
    print(f"\n{len(todo)} of {len(rules)} rules need a source.")
    return 1 if todo else 0


if __name__ == "__main__":
    sys.exit(main())
