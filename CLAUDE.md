# CLAUDE.md

Offline clinic OPD app (Streamlit, pydantic, pytest, Python 3.14). Patient quiz and OCR scan, staff board, doctor summary and a deterministic dosage-check engine. See `../PROJECT_OVERVIEW.md`, `docs/DOSING_LOGIC.md` and `docs/DOSING_DATA_ISSUES.md`.

## Commands
Run from `hack-binary-solo/` using the local venv:
- Demo launcher: `./run_demo.sh [--demo-mode]` (startup check, demo login and synthetic patients if none, then the app); check only: `scripts/startup_check.py`
- App: `.venv/bin/streamlit run main_app.py` (OCR needs Ollama on localhost; dosing does not)
- Tests: `.venv/bin/python -m pytest -q` (dosing only: `tests/test_dosing_*.py`)
- Dosing demo as text: `.venv/bin/python scripts/dosing_demo.py`
- Create a login: `.venv/bin/python scripts/create_user.py <name> <doctor|staff>`
- Data checks: `scripts/validate_graph.py`, `scripts/list_boundary_overlaps.py`

## Layout
- `intake/` quiz engine, red flags, summary, Streamlit pages (`intake/ui/`, incl. `dosing_panel.py`, `dosage.py`)
- `records/` PatientRecord schema and local JSON store (`data_local/`, gitignored)
- `ocr/` local vision-model transcription and formulary matching
- `dosing/` the dosage engine: `mapper` (quiz to context), `rules`, `calc`, `products`, `safety`, `interactions`, `history`, `engine`, `service`, `audit`, `demo`; data in `dosing/data/`
- Formulary: verbatim copy at `data/dosesafe_formulary_v2.json` (original in `../Final_Drugs_data/`); `DOSING_FORMULARY_PATH` overrides. Do not edit it

## Hard rules (do not break)
- No LLM, network or randomness in `dosing/`. Pure functions: same input, same output.
- Every clinical number comes from the formulary JSON. Never hard-code doses, limits, thresholds or interactions. If a field is missing, refuse or return `needs_input`; never guess.
- Never edit the formulary JSON, the quiz graph (`data/intake_graph.json`) or the red-flag rules. Log data problems in `docs/DOSING_DATA_ISSUES.md`.
- "Not sure" and "not asked" are unknown, never "no".
- Hard blocks are overridable only with a reason category plus a written reason of at least 10 characters, and are audit-logged.
- Everything is prototype data. Never mark anything clinically verified. Keep the "Prototype data, not clinically verified" banner.
- Patient quiz answers are immutable; doctor entries are stored separately (`doctorEdits`, `visitHistory`, `dosingChecks`).
- Patients never see dosing output.

## Conventions
- Match surrounding code style and comment density; no new frameworks.
- Engine user-facing strings live in `dosing/messages.py` (English now; Hindi and Marathi to be added).
- Tests derive expected values from the formulary JSON, not typed-in numbers (except arithmetic tests).
- Open items needing a clinician or data: growth tables (`dosing/data/growth_reference.json` is "needs data"), NSAID heart wording, which free-text contraindications should hard-block.
