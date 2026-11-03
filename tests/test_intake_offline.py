"""Network behaviour: the whole intake flow touches no socket; the optional LLM paragraph only talks
to localhost Ollama and falls back to the template otherwise. Same spy pattern as test_service_offline."""
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from intake import llm_summary
from intake.models import load_graph
from intake.redflags import load_rules
from intake.summary import build_summary, template_paragraph
from intake.synthetic import PATIENTS, run_bank
from records import store

G, RULES = load_graph(), load_rules()
reply = {"content": "The patient reports chest pain that started suddenly.", "calls": 0, "body": None}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_POST(self):
        reply["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        reply["calls"] += 1
        b = json.dumps({"message": {"content": reply["content"]}}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers()
        self.wfile.write(b)


@pytest.fixture()
def net(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("OLLAMA_URL", f"http://localhost:{srv.server_port}")
    reply.update(calls=0, body=None, content="The patient reports chest pain that started suddenly.")
    contacted = []
    real = socket.socket.connect

    def spy(self, addr):
        contacted.append(addr[0] if isinstance(addr, tuple) else str(addr))
        return real(self, addr)
    monkeypatch.setattr(socket.socket, "connect", spy)
    yield contacted
    srv.shutdown()


def summary():
    r = run_bank(G, RULES, PATIENTS["adult_chest_pain"]).finish()
    return build_summary(r)


def test_full_intake_and_storage_use_no_network(net, tmp_path):
    for ov in PATIENTS.values():
        r = run_bank(G, RULES, ov).finish()
        store.save(r, tmp_path)
        build_summary(r)
    assert net == []


def test_llm_off_by_default_makes_no_call(net):
    res = llm_summary.draft_paragraph(summary())
    assert res.source == "template" and res.text == template_paragraph(summary()) and net == [] and reply["calls"] == 0


def test_llm_localhost_only_and_labelled(net):
    res = llm_summary.draft_paragraph(summary(), enabled=True)
    assert res.source == "ai-drafted" and "AI-drafted" in llm_summary.LABEL
    assert net and set(net) <= {"127.0.0.1", "::1"}, net
    assert reply["body"]["options"]["temperature"] == 0 and reply["body"]["stream"] is False


def test_llm_prompt_contains_no_numbers():
    facts = llm_summary.fact_sheet(summary())
    assert not any(c.isdigit() for c in facts)
    assert "severe" in facts and "Chest pain" in facts


@pytest.mark.parametrize("bad", [
    "Give 500 mg now.", "Take two tablets daily.", "This is likely a heart attack, I diagnose it.",
    "Severity was 8 out of 10.", "I recommend aspirin.", "", "Probably angina.",
])
def test_llm_output_with_numbers_doses_or_diagnosis_falls_back(net, bad):
    reply["content"] = bad
    res = llm_summary.draft_paragraph(summary(), enabled=True)
    assert res.source == "template" and res.text == template_paragraph(summary())


def test_llm_falls_back_when_ollama_down(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:9")
    res = llm_summary.draft_paragraph(summary(), enabled=True, timeout=2)
    assert res.source == "template" and "unavailable" in res.reason


def test_non_local_ollama_url_rejected(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://example.com:11434")
    with pytest.raises(ValueError):
        llm_summary.draft_paragraph(summary(), enabled=True)


def test_intake_package_only_imports_requests_in_llm_module():
    from pathlib import Path
    root = Path(llm_summary.__file__).parent
    offenders = [f.name for f in list(root.glob("*.py")) + list((root.parent / "records").glob("*.py"))
                 if "import requests" in f.read_text() and f.name != "llm_summary.py"]
    assert offenders == []


def test_smoke_script_runs(capsys):
    import runpy
    from pathlib import Path
    ns = runpy.run_path(str(Path(__file__).resolve().parent.parent / "scripts" / "intake_smoke.py"))
    assert ns["main"]() == 0
    out = capsys.readouterr().out
    assert out.count("PATIENT ") == 3 and "RF_INFANT_FEVER_UNDER_3_MONTHS" in out
