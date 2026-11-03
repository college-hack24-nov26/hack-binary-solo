# MediKiosk OPD: patient kiosk, staff desk, doctor workstation

An offline clinic OPD app. One laptop runs the server; the waiting-area tablet and the staff and doctor screens open it over the hospital LAN with no internet. FastAPI serves the API and the built React app from one origin. Synthetic data only. **Prototype data, not clinically verified.**

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/create_user.py <username> <doctor|staff>    # once; writes data/users.json (gitignored)
.venv/bin/python scripts/run_server.py                               # builds web/ if needed, then serves on :8000
```
Open `http://<this-computer>:8000/` and pick a screen:

| Screen | Address | Who |
|---|---|---|
| Patient kiosk | `/kiosk` | the tablet: language, consent, one question per screen, body map, review, doctor choice, token slip |
| Staff desk | `/staff` | live board (red flags, help requests), patient panel, vitals, scans |
| Doctor workstation | `/doctor` | my queue, summary, vitals, scan confirmation, notes, Dosage check, dosing record, audit log |
| Component gallery | `/gallery` | every component in every state (development builds or `DEMO_MODE=1`) |

Run options:
```bash
DEMO_MODE=1 .venv/bin/python scripts/run_server.py                    # Load demo patient, red DEMO bar, /gallery
OFFLINE_STRICT=1 DEMO_MODE=1 .venv/bin/python scripts/run_server.py   # any non-localhost connection raises and is logged
./run_demo.sh --demo-mode                                             # startup check, demo login and patients if none, then the server
OPD_MINUTES_PER_PATIENT=12 ...                                        # wait estimate on the token slip (default 10)
```
One uvicorn worker only: records are JSON files and the audit log is a hash chain, guarded by one process-wide lock (`api/deps.py`). OCR scanning needs Ollama on localhost; the quiz, boards and dosing do not.

**Pin the tablet:** open `/kiosk` in Chrome, add it to the home screen, then use Android screen pinning (Settings > Security > App pinning) or a kiosk-browser app, so patients cannot reach other screens. The kiosk itself has no links to `/staff` or `/doctor`.

## Develop and test
```bash
.venv/bin/python -m pytest -q                       # Python: domain + API (tests/api)
npm --prefix web ci                                 # once (needs the npm registry or a cache)
npm --prefix web run dev                            # Vite on :5173, proxies /api to :8000 (start run_server.py --no-build)
npm --prefix web test                               # Vitest
npm --prefix web run e2e                            # Playwright: kiosk, staff, doctor, hardening (axe, offline, viewports)
(cd web && SCREENS=kiosk npx playwright test e2e/screens.spec.ts)    # screenshots into docs/screens/
npm --prefix web run gen:api                        # regenerate web/src/api/generated.ts from the OpenAPI schema
```
Docs: `docs/REBUILD_PLAN.md` (parity, permissions, API), `docs/DESIGN.md` (tokens and review log), `docs/UI_HIGHLIGHTS.md`, `docs/DEMO_SCRIPT.md`, `docs/DOSING_LOGIC.md`, `docs/DOSING_DATA_ISSUES.md`.

| Piece | Where |
|---|---|
| API (routers, auth, lock, SSE, kiosk sessions) | `api/` (`api/main.py` app factory, OpenAPI at `/api/openapi.json`) |
| React app | `web/src/` (`kiosk/`, `staff/`, `doctor/`, `components/`, `dosing/`, `gallery/`) |
| Quiz engine, red flags, summary, offline guard | `intake/` |
| Patient record and store | `records/` (folder `data_local/`, gitignored) |
| Dosage engine and audit log | `dosing/` |
| Local OCR | `ocr/` |

---

# OCR (Qwen3-VL via local Ollama)

Offline only: the one network call is to `localhost:11434`. AI drafts, the doctor confirms. Staff or a doctor attach a photo to a patient's token (`POST /api/patients/{token}/scans`, `<input capture>` works over plain HTTP); the draft waits until a doctor confirms or discards it on the Timeline.

```bash
.venv/bin/python scripts/make_fixtures.py  # 3 synthetic Rx + 1 lab report -> fixtures/
.venv/bin/python scripts/ocr_smoke.py      # real model, per-field PASS/FAIL + latency
```
| Piece | File |
|---|---|
| `extract()` / `health()` | `ocr/service.py` |
| VLM prompt, schema | `ocr/prompt.py`, `ocr/schema.py` |
| Frequency parser, fuzzy matcher, needsReview | `ocr/frequency.py`, `ocr/formulary.py`, `ocr/postprocess.py` |
| Temp image lifecycle | `ocr/session.py` |

Config (env): `OCR_MODEL` (default `qwen3-vl:8b-instruct`), `OLLAMA_URL` (must be localhost), `OCR_MAX_EDGE`, `OCR_KEEP_ALIVE`, `OCR_SESSION_TTL_S`, `OCR_REVIEW_THRESHOLD`.

---

# Intake quiz (adaptive questions, red flags, doctor summary)

Offline, synthetic data only. AI drafts, the doctor decides. No diagnosis or advice in patient-facing text.

```bash
.venv/bin/python scripts/validate_graph.py          # graph checks: targets, cycles, unreachable, never-ends, translations
.venv/bin/python scripts/intake_cli.py [en|hi|mr]    # terminal simulator
.venv/bin/python scripts/intake_smoke.py             # 3 synthetic patients: record + doctor summary
.venv/bin/python scripts/list_unsourced_rules.py     # red-flag rules still lacking a source
.venv/bin/python scripts/list_unreviewed_translations.py
```

| Piece | File |
|---|---|
| Question graph (data) | `data/intake_graph.json` (pydantic: `intake/models.py`) |
| Condition language | `intake/conditions.py` (equals, in, gte, lte, all, any, not, answered, unanswered, regionsAny, regionsAll) |
| Pure engine | `intake/engine.py`: `next_node`, `recompute_path`, `validate_graph` |
| Red-flag rules (DRAFT) | `data/red_flags.json`, `intake/redflags.py` |
| Record + local JSON store | `records/schema.py`, `records/build.py`, `records/store.py` |
| Doctor summary, edit tracking | `intake/summary.py`; optional local-LLM paragraph `intake/llm_summary.py` |
| Kiosk over HTTP | `api/routers/kiosk.py`, `api/sessions.py` (sessions rebuilt from the saved record after a restart) |

Answer semantics: **"Not sure" (`unsure`) is an answer; skipped (`__skipped__`) is not.** Both continue the flow and both put the item in `dosingInputs.missing`. "Not sure" never matches a concrete value in any rule.

Red flags: all 10 rules are drafts with `source: null`, `sourceChecked: false`; every screen labels them "Draft rule, source check pending". Patients see only each rule's patient message.

## Translations need native review
Every node's Hindi and Marathi, the red-flag patient messages, the body-region labels, the doctors' specialty/floor/line names and the kiosk UI strings (`web/src/i18n/kiosk.json`) are **machine-drafted, needs native review**. `scripts/list_unreviewed_translations.py` lists all of them.

## Body map (Site and Radiation questions)
- **Regions and artwork:** `data/body_regions.json`: 54 stable region ids, own polygons (no third-party art), en/hi/mr labels. **`right`/`left` are always the patient's own side**; the kiosk says "Patient's right" / "Patient's left".
- **Input:** the kiosk highlights taps in the browser and offers "Choose from a list" at all times; the server builds and validates the answer with `bodymap.make_answer` (`{regions, view, inputMode}` + `special` for tell-doctor / none).
- **Doctor:** regions in words in en/hi/mr plus small diagrams (site red, spreads-to orange).

---

# Demo
```bash
.venv/bin/python scripts/reset_demo_data.py         # clear demo records and demo audit entries
.venv/bin/python scripts/dosing_demo.py             # the three fixtures as text (source of the expected numbers)
```
Click-through: `docs/DEMO_SCRIPT.md`. Video of the 60-second judge path: `docs/screens/demo.webm`.

| Feature | Where |
|---|---|
| Offline badge, probe, `OFFLINE_STRICT` guard | `intake/offline.py`, `GET /api/system/offline-status`, `web/src/components/OfflineBadge.tsx` |
| Demo fixtures, Load demo patient, reset | `fixtures/demo/*.json`, `dosing/demo.py`, `api/routers/demo.py`, `scripts/reset_demo_data.py` |
| Result card wording (four statuses, checklist, override) | `api/result_card.py`, `web/src/dosing/ResultCard.tsx`, `web/src/doctor/DosageCheck.tsx` |
| Audit log (doctor only, read-only) | `dosing/audit.py`, `dosing/audit_view.py`, `api/routers/audit.py`, `web/src/doctor/AuditLog.tsx` |
| Medicines from confirmed scans | `dosing/ocr_meds.py` |

Env: `DEMO_MODE`, `OFFLINE_STRICT`, `OFFLINE_PROBE_HOST`, `OFFLINE_PROBE_PORT`, `OFFLINE_PROBE_TIMEOUT_S` (2), `OFFLINE_CHECK_INTERVAL_S` (30), `OPD_MINUTES_PER_PATIENT` (10), `HTTPS` (marks the login cookie Secure). Everything is synthetic and **not clinically verified**.
