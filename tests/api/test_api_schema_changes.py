"""The two small changes to protected packages: optional queue/scan fields on PatientRecord and room/floor-line fields on Doctor."""
import json
import re

from intake.doctors import load_doctors
from intake.models import load_graph
from intake.redflags import load_rules
from intake.synthetic import run_bank
from records.schema import PatientRecord

from api.views import doctor_out


def _contrast(a: str, b: str) -> float:
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_old_records_without_queue_or_scan_fields_still_load():
    rec = run_bank(load_graph(), load_rules(), token="PT-OLDAAB").finish()
    raw = json.loads(rec.model_dump_json())
    for k in ("queueNumber", "queueDate", "finishedAt", "pendingScans"):
        del raw[k]
    old = PatientRecord.model_validate(raw)
    assert (old.queueNumber, old.queueDate, old.finishedAt, old.pendingScans) == (None, None, None, [])


def test_every_doctor_has_a_room_and_a_readable_floor_line():
    for d in load_doctors():
        assert d.room and d.floor and d.lineName and re.fullmatch(r"#[0-9A-F]{6}", d.lineColor)
        for lang in ("en", "hi", "mr"):
            assert d.floor.get(lang) and d.lineName.get(lang)
        out = doctor_out(d)
        assert _contrast(out["lineTextColor"], d.lineColor) >= 4.5          # text printed on the stripe (AA)
        assert d.lineColor.upper() != "#B42318"                              # red means "stop" in this product, never a route


def test_doctors_file_still_says_synthetic_and_machine_drafted():
    raw = json.loads((load_graph.__globals__["ROOT"] / "data" / "doctors.json").read_text(encoding="utf-8"))
    assert "SYNTHETIC" in raw["_note"] and raw["translationStatus"] == "machine-drafted, needs native review"


def test_new_web_strings_are_listed_as_unreviewed(capsys):
    import importlib.util
    root = load_graph.__globals__["ROOT"]
    spec = importlib.util.spec_from_file_location("lut", root / "scripts" / "list_unreviewed_translations.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()
    out = capsys.readouterr().out
    web = json.loads((root / "web" / "src" / "i18n" / "kiosk.json").read_text(encoding="utf-8"))
    assert web["translationStatus"] == "machine-drafted, needs native review"
    for key, v in web["strings"].items():
        assert f"web  {key}" in out and v["en"] and v["hi"] and v["mr"]
    assert "doctor dr_general" in out
