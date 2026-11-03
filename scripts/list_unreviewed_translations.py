"""List every graph node (and red-flag message) whose Hindi/Marathi is still machine-drafted."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intake.models import TRANSLATION_STATUS, load_graph  # noqa: E402
from intake.bodymap import catalog  # noqa: E402
from intake.redflags import load_rules  # noqa: E402


def main() -> int:
    g, rules = load_graph(), load_rules()
    todo = [n for n in g.nodes if n.translationStatus == TRANSLATION_STATUS]
    for n in todo:
        print(f"node {n.id:18s} {len(n.options):2d} options  {n.translationStatus}")
    for r in rules:
        print(f"rule {r.id}  patientMessage  {r.patientMessage.translationStatus}")
    regions = catalog().regions
    print(f"regions ({len(regions)}) in data/body_regions.json  {catalog().translationStatus}")
    root = Path(__file__).resolve().parent.parent
    web = json.loads((root / "web" / "src" / "i18n" / "kiosk.json").read_text(encoding="utf-8"))
    for key in web["strings"]:
        print(f"web  {key:18s} kiosk UI string  {web['translationStatus']}")
    docs = json.loads((root / "data" / "doctors.json").read_text(encoding="utf-8"))
    for d in docs["doctors"]:
        print(f"doctor {d['id']:12s} specialty, floor, lineName  {docs['translationStatus']}")
    print(f"\n{len(todo)} of {len(g.nodes)} nodes + {len(rules)} rule messages + {len(regions)} body regions + {len(web['strings'])} web kiosk "
          f"strings + {len(docs['doctors'])} doctors need native review (hi, mr). UI chrome: intake/ui/strings.py, web/src/i18n/kiosk.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
