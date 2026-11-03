"""The formulary ships inside the repo; the startup check works without Ollama."""
import filecmp
import sys
from pathlib import Path

import pytest

from dosing import config, formulary

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import startup_check  # noqa: E402


def test_default_formulary_is_inside_the_repo_and_loads():
    p = config.Config().formulary_path
    assert ROOT in p.parents and p.exists()
    assert formulary.validate(formulary.load(p).raw) == []


def test_repo_copy_is_verbatim_when_the_original_is_present():
    orig = ROOT.parent / "Final_Drugs_data" / "dosesafe_formulary_v2.json"
    if not orig.exists():
        pytest.skip("original folder not present")
    assert filecmp.cmp(orig, config.Config().formulary_path, shallow=False)


def test_formulary_path_can_be_overridden(monkeypatch, tmp_path):
    monkeypatch.setenv("DOSING_FORMULARY_PATH", str(tmp_path / "x.json"))
    assert config.Config.from_env().formulary_path == tmp_path / "x.json"


def test_missing_ollama_is_a_warning_not_a_failure(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:1")
    checks = startup_check.check_all()
    oll = [c for c in checks if "Ollama" in c.name or c.name.startswith("OCR model")]
    assert oll and all(not c.ok and not c.critical for c in oll)
    assert not [c for c in checks if not c.ok and c.critical]          # dosing demo is still ready
    assert any(c.name == "dosing engine self-test" and c.ok for c in checks)


def test_ollama_status_reports_model_presence(monkeypatch):
    import io, json, urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: io.BytesIO(json.dumps({"models": [{"name": "qwen3-vl:8b-instruct"}]}).encode()))
    assert startup_check.ollama_status("http://localhost:11434", "qwen3-vl:8b-instruct")[:2] == (True, True)
    assert startup_check.ollama_status("http://localhost:11434", "other:1b")[:2] == (True, False)


def test_launcher_check_only_exits_zero_without_starting_the_app(monkeypatch):
    import run_demo
    monkeypatch.setattr(sys, "argv", ["run_demo.py", "--check-only"])
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:1")
    assert run_demo.main() == 0
