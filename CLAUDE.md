# CLAUDE.md

Offline clinic OPD app: FastAPI (`api/`) + React (`web/`), pydantic, pytest, Python 3.14. Patient kiosk (tablet), staff desk, doctor workstation with a deterministic dosage-check engine. Streamlit was retired (see `docs/REBUILD_PLAN.md`). See `../PROJECT_OVERVIEW.md`, `docs/DOSING_LOGIC.md` and `docs/DOSING_DATA_ISSUES.md`.

## Commands
Run from `hack-binary-solo/` using the local venv:
- Demo launcher: `./run_demo.sh [--demo-mode]` (startup check, demo login and synthetic patients if none, then the server); check only: `scripts/startup_check.py`
- App: `.venv/bin/python scripts/run_server.py` (builds `web/` if needed; one uvicorn worker on 0.0.0.0:8000; `DEMO_MODE=1`, `OFFLINE_STRICT=1`). OCR needs Ollama on localhost; dosing does not
- Tests: `.venv/bin/python -m pytest -q` (API: `tests/api/`; dosing only: `tests/test_dosing_*.py`); web: `npm --prefix web test` (Vitest), `npm --prefix web run e2e` (Playwright via `scripts/e2e_server.py`, temp data)
- Web: `npm --prefix web run dev` (proxies /api to :8000), `npm --prefix web run gen:api` after any API schema change (commit `web/src/api/generated.ts`)
- Dosing demo as text: `.venv/bin/python scripts/dosing_demo.py`
- Create a login: `.venv/bin/python scripts/create_user.py <name> <doctor|staff>`
- Data checks: `scripts/validate_graph.py`, `scripts/list_boundary_overlaps.py`

## Layout
- `api/` FastAPI: `main.py` (create_app), `deps.py` (WRITE_LOCK, login sessions, roles), `routers/` (system, auth, kiosk, identity, kiosk_scans, patients, staff, staff_patients, doctor, doctor_visits, ocr, dosing, audit, demo), `identity_provider.py` (PinProvider; OtpProvider is a stub), `kiosk_identity.py` (identity sessions, rate limits), `scan_jobs.py` (background OCR for kiosk scans), `sessions.py` (kiosk sessions), `events.py` (SSE), `result_card.py` (card wording)
- `web/` React 19 + Vite + Tailwind v4: `src/kiosk`, `src/staff`, `src/doctor`, `src/components`, `src/dosing`, `src/gallery`; tokens in `src/styles/app.css` (from `docs/DESIGN.md`); kiosk strings `src/i18n/kiosk.json`
- `intake/` quiz engine, red flags, summary, offline guard
- `records/` PatientRecord schema and local JSON store (`data_local/`, gitignored); `identity.py` (mask, Fernet, HMAC lookup, argon2id PIN), `patients.py` (identity store), `identity_audit.py`, `scanfiles.py`
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
- Patients never see dosing output, diagnoses, red-flag rule ids or other patients (the kiosk shows only `patientMessage`).
- The server is the single source of truth: the web app never computes quiz flow, red flags, doses, rounding or blanking. No dose number renders unless `status == "ok"`.
- Every record or audit write holds `api.deps.WRITE_LOCK`; run one worker. Confirm uses the server's cached result, never a client-sent one.
- Offline: no CDN, remote fonts/icons/analytics; `tests/test_offline.py` scans `api/` and `web/src` for outside URLs. Never use browser speech recognition (it sends audio to a server); read-aloud only with `voice.localService`.

- No OTP, "verified" or similar claim without a real provider. There is no SMS offline: identity is identifier + 4-digit PIN (`PinProvider`). `OtpProvider` stays a stub that raises; never add a fake OTP screen.
- ABHA is an unverified identifier: format check only, label "ABHA number (optional)". No government logos, card imitations, "NDHM" or "secure" claims.
- No plaintext identifier or PIN on disk or in logs. Identifiers are Fernet-encrypted with an HMAC lookup hash, PINs are argon2id over a peppered input, UI and audit show masked values only. `tests/api/test_api_identity.py::test_no_plaintext_identifier_or_pin_on_disk_or_in_logs` must keep passing; the key file `data_local/identity.key` is never committed.
- Scanned text (kiosk or staff) is patient-supplied and unverified until a doctor uses it: only the doctor's "Use as current medicines" writes it to the timeline (with `confirmedBy` and per-item provenance). It never reaches `dosing/` by any other path. The kiosk shows no clinical meaning for scanned medicines.
- No network calls added by identity or scan code (`OFFLINE_STRICT=1` must pass). No government branding anywhere.
- Declining consent or the PIN never blocks care: anonymous walk-in and "Ask staff" always work.

## Conventions
- Match surrounding code style and comment density; no new frameworks.
- Engine user-facing strings live in `dosing/messages.py` (English now; Hindi and Marathi to be added). Kiosk UI strings: `web/src/i18n/kiosk.json` (hi/mr machine-drafted).
- UI design rules and review log: `docs/DESIGN.md`; check new screens against its section 8 checklist and `web/e2e/hardening.spec.ts` (axe, viewports).
- Tests derive expected values from the formulary JSON, not typed-in numbers (except arithmetic tests).
- Open items needing a clinician or data: growth tables (`dosing/data/growth_reference.json` is "needs data"), NSAID heart wording, which free-text contraindications should hard-block.
