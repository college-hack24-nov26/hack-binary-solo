"""Startup check: is everything the demo needs present? Dosing needs no Ollama; OCR does, so a missing Ollama or
model is reported as a warning and never stops the demo.
Run: .venv/bin/python scripts/startup_check.py   (exit code 1 only if something the dosing demo needs is missing)"""
import importlib
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    critical: bool = True          # False: a warning, the demo still works

    @property
    def mark(self) -> str:
        return "OK  " if self.ok else ("FAIL" if self.critical else "WARN")


def ollama_status(url: str, model: str, timeout: float = 2.0) -> tuple[bool, bool, str]:
    """-> (server reachable, model present, detail). Never raises."""
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/tags", timeout=timeout) as r:
            names = [m.get("name", "") for m in json.loads(r.read()).get("models", [])]
    except (urllib.error.URLError, OSError, ValueError) as e:
        return False, False, f"Ollama not reachable at {url} ({type(e).__name__})"
    have = any(n == model or n.split(":")[0] == model.split(":")[0] and model.endswith(":latest") or n.startswith(model) for n in names)
    return True, have, (f"model {model} present" if have else f"Ollama is running but model {model} is missing (ollama pull {model})")


def check_all() -> list[Check]:
    out: list[Check] = []
    out.append(Check("python", sys.version_info >= (3, 10), f"{sys.version.split()[0]} (3.10 or newer needed)"))
    for mod in ("streamlit", "pydantic", "pandas", "PIL", "requests"):
        try:
            importlib.import_module(mod)
            out.append(Check(f"package {mod}", True, "installed"))
        except ImportError:
            out.append(Check(f"package {mod}", False, "missing: pip install -r requirements.txt"))
    try:
        from dosing import config, formulary
        cfg = config.Config.from_env()
        if not cfg.formulary_path.exists():
            out.append(Check("formulary", False, f"not found at {cfg.formulary_path} (set DOSING_FORMULARY_PATH or restore data/dosesafe_formulary_v2.json)"))
        else:
            f = formulary.load(cfg.formulary_path)
            issues = formulary.validate(f.raw)
            out.append(Check("formulary", not issues, f"v{f.version}, {len(f.drugs)} drugs at {cfg.formulary_path}"
                             + (f"; {len(issues)} unsupported shape(s): {issues[0]}" if issues else "")))
            from dosing import mapper
            from dosing.engine import Request, evaluate
            ctx = mapper.map_quiz({"consent": "agree", "age_years": 4, "sex": "male", "weight_kg": 16, "allergies": ["none"], "meds_any": "no",
                                   "kidney": "no", "liver": "no", "diabetes": "no", "hypertension": "no", "asthma": "no", "chief_complaint": "fever"})
            res = evaluate(Request("paracetamol", ctx, "pain/fever", doctor_inputs={"weight_kg": 16}), cfg)
            out.append(Check("dosing engine self-test", res["status"] == "ok" and res["dose_mg"] is not None,
                             f"paracetamol child dose {res['dose_mg']} mg ({res['status']})"))
    except Exception as e:  # noqa: BLE001 - the check must report, not crash
        out.append(Check("dosing engine", False, f"{type(e).__name__}: {e}"))
    try:
        from intake.models import load_graph
        out.append(Check("quiz graph", True, f"{len(load_graph().nodes)} nodes"))
    except Exception as e:  # noqa: BLE001
        out.append(Check("quiz graph", False, f"{type(e).__name__}: {e}"))
    try:
        from ocr.auth import has_users
        from ocr.config import load_settings
        s = load_settings()
        out.append(Check("login users", has_users(s.users_file), "present" if has_users(s.users_file) else
                         "none yet: scripts/run_demo.py creates a demo login, or run scripts/create_user.py", critical=False))
        up, have, detail = ollama_status(s.ollama_url, s.model)
        out.append(Check("Ollama (OCR only)", up, detail if not up else f"reachable at {s.ollama_url}", critical=False))
        if up:
            out.append(Check(f"OCR model {s.model}", have, detail, critical=False))
        else:
            out.append(Check(f"OCR model {s.model}", False, "not checked; OCR scan will be unavailable, dosing and quiz still work", critical=False))
    except Exception as e:  # noqa: BLE001
        out.append(Check("settings", False, f"{type(e).__name__}: {e}", critical=False))
    return out


def main() -> int:
    checks = check_all()
    for c in checks:
        print(f"[{c.mark}] {c.name}: {c.detail}")
    bad = [c for c in checks if not c.ok and c.critical]
    warn = [c for c in checks if not c.ok and not c.critical]
    print(("\nNot ready: fix the FAIL lines above." if bad else "\nReady for the dosing demo.")
          + (" OCR scan will be unavailable (see WARN lines)." if any("Ollama" in c.name or "OCR" in c.name for c in warn) else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
