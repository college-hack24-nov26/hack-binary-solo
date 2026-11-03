"""Run fixtures through the real local model; print per-field results + latency.
Run: .venv/bin/python scripts/ocr_smoke.py [--prints]   (--prints shows full extracted JSON; synthetic data only)"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ocr import ollama_client, service  # noqa: E402
from ocr.config import load_settings  # noqa: E402

FIX = Path(__file__).resolve().parent.parent / "fixtures"
norm = lambda x: re.sub(r"[\s.]", "", (x or "").lower())  # noqa: E731


def check(label, ok, got):
    print(f"   {'PASS' if ok else 'FAIL'}  {label:<34} got: {got}")
    return ok


def main():
    s = load_settings()
    h = service.health(s)
    print(f"model={s.model} max_edge={s.max_edge}  health={ {k: h[k] for k in ('ollamaUp', 'modelPresent')} }")
    if not (h["ollamaUp"] and h["modelPresent"]):
        sys.exit("Ollama down or model missing. `ollama list` / `ollama pull <tag>`")
    t = time.time(); ollama_client.warm(s); print(f"warm-up: {time.time() - t:.1f}s\n")
    passed = total = 0
    for png in sorted(FIX.glob("*.png")):
        exp = json.loads(png.with_suffix(".expected.json").read_text())
        r = service.extract(png.read_bytes(), True, "staff", s)
        print(f"== {png.name}   latency={r.get('latencyS')}s attempts={r.get('attempts')}")
        if not r["ok"]:
            print("   ERROR", r["error"], "needsManualEntry=", r["needsManualEntry"]); total += 1; continue
        res = r["result"]
        if "--prints" in sys.argv:
            print(json.dumps(res, indent=1))
        total += 1; passed += check("documentType", res["documentType"] == exp["documentType"], res["documentType"])
        if "meds" in exp:
            for name, freq in exp["meds"]:
                m = next((m for m in res["medications"] if name.lower() in m["nameAsWritten"].lower()), None)
                total += 1; passed += check(f"med name '{name}' verbatim", m is not None, m and m["nameAsWritten"])
                if m:
                    total += 1; passed += check(f"  frequency '{freq}'", norm(m["frequencyAsWritten"]) == norm(freq), m["frequencyAsWritten"])
                    print(f"        parsed={m['frequencyParsed']['display']} generic={m['suggestedGeneric']} "
                          f"score={m['matchScore']} conf={m['confidence']} review={m['needsReview']} {m['reviewReasons']}")
            total += 1; passed += check("no extra medications", len(res["medications"]) == len(exp["meds"]), len(res["medications"]))
        for test, val, unit in exp.get("labs", []):
            l = next((l for l in res["labResults"] if test.lower() in l["test"].lower()), None)
            total += 1; passed += check(f"lab '{test}' value", bool(l) and norm(l["value"]) == norm(val), l and (l["value"], l["unit"]))
        if res["unreadable"] or res["warnings"]:
            print("   unreadable:", res["unreadable"], "warnings:", res["warnings"])
    print(f"\nchecks passed: {passed}/{total}")


if __name__ == "__main__":
    main()
