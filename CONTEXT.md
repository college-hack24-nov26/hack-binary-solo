# CONTEXT.md - hack-binary-solo

Hand-off file for a brand-new chat. Built only from the code, tests, docs and data in the repo folder `hack-binary-solo/`
(read 2026-11-04). Anything not in the repo is marked "not found". Git history was not read.
Two things sit OUTSIDE the repo folder, one level up: `../Final_Drugs_data/` (the dosing formulary) and `../PROJECT_OVERVIEW.md` (not read).

## 1. Project in 5 lines
1. What: an offline clinic OPD app. A patient answers an adaptive quiz (en/hi/mr); staff see red flags; a doctor gets a summary and a deterministic dosage-check engine; old paper records can be scanned by a local vision model.
2. Users: patients (kiosk quiz), staff (red-flag board, vitals), doctors (summary, dosage check, audit log). Patients never see dosing output.
3. Offline/local-only: only allowed outbound call is `localhost:11434` (Ollama); data are local JSON files; an offline badge and `OFFLINE_STRICT` guard prove it. Dosing code has no network, no LLM, no randomness.
4. Status: prototype. Every formulary drug is `verified: false`; the UI shows "Prototype data, not clinically verified". Synthetic data only. UI: FastAPI (`api/`) + React (`web/`) since 2026-11-04 (Streamlit retired). Tests (before the identity work): 829 Python, 17 Vitest, 16 Playwright; see section 11 for the current additions.
5. Hackathon context: not stated in code. Folder is `Phaltan_hacktahon`; a "Hackathon 2K26 at College of Engineering Phaltan, 3-4 Nov 2026" is NOT in the repo (hackathon name/rules/judging: not found). `docs/DEMO_SCRIPT.md` is a ~4 minute demo script.

## 2. Tech stack, run, tests, demo
Stack: Python 3.14 (also 3.13), FastAPI + uvicorn (one worker), pydantic, pytest, pillow, requests; web: Vite, React 19, TypeScript, Tailwind v4, TanStack Query, Zod, lucide-react, self-hosted Noto Sans/Devanagari, Vitest, Playwright + axe.
`requirements.txt`: pillow, pydantic, requests, pytest, fastapi, uvicorn, python-multipart, httpx. Web deps: `web/package.json`. OCR = Qwen3-VL via local Ollama (`OCR_MODEL`, default `qwen3-vl:8b-instruct`). Optional doctor-summary paragraph = local Ollama `INTAKE_LLM_MODEL` (default `qwen3:8b`), off by default.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                                   # optional; defaults work
.venv/bin/python scripts/create_user.py <name> <doctor|staff>   # once; writes data/users.json (gitignored)
.venv/bin/python scripts/run_server.py               # builds web/ if needed, serves /kiosk, /staff, /doctor and /api on :8000
.venv/bin/python -m pytest -q                          # 829 passed in ~25 s; API: tests/api; dosing only: tests/test_dosing_*.py
npm --prefix web test; npm --prefix web run e2e        # 17 Vitest; 16 Playwright (kiosk, staff, doctor, axe, offline, viewports)
.venv/bin/python scripts/dosing_demo.py                # the 3 demo patients as text (temp data folder)
.venv/bin/python scripts/reset_demo_data.py            # remove demo records + demo audit entries (--rechain-others)
DEMO_MODE=1 .venv/bin/python scripts/run_server.py                    # demo: "Load demo patient" + red DEMO bar + /gallery
OFFLINE_STRICT=1 DEMO_MODE=1 .venv/bin/python scripts/run_server.py   # non-localhost connect raises + is logged
```
Other scripts: `validate_graph.py`, `intake_cli.py [en|hi|mr]`, `intake_smoke.py`, `make_fixtures.py` (writes `fixtures/*.png` + `.expected.json`; both gitignored), `ocr_smoke.py` (needs Ollama), `list_unsourced_rules.py`, `list_unreviewed_translations.py`, `list_boundary_overlaps.py`, `list_region_followups.py`.
Dosing and the quiz need no Ollama; OCR scanning does.

Env flags (from `.env.example`, `dosing/config.py`, `intake/offline.py`):
| Flag | Default | Effect |
|---|---|---|
| `DEMO_MODE` | 0 | Shows "Load demo patient" (doctor role). Also sets dosing demo behaviour (below). |
| `DOSING_DEMO_MODE` | 0 | Forces `allow_unverified` on; every result carries `demo` + banner "DEMO - UNVERIFIED DATA"; panel shows a red bar. |
| `DOSING_ALLOW_UNVERIFIED` | false | When off, UNVERIFIED rules are refused; when on they are computed and marked. |
| `OFFLINE_STRICT` | 0 | Patches socket connects: any non-loopback address raises `OfflineViolation` and is logged (logger `offline`); public probe skipped. |
| `OFFLINE_PROBE_HOST/PORT/TIMEOUT_S` | 1.1.1.1 / 443 / 2 | Public-host TCP probe for the badge (never used by the app). |
| `OFFLINE_CHECK_INTERVAL_S` | 30 | Badge refresh. |
| `DOSING_ML_STEP` | 0.5 | Liquid volume rounding step (mL). |
| `DOSING_ABW_FACTOR` | formulary `factor_default` | Adjusted body weight factor. |
| `DOSING_FORMULARY_PATH` | `../Final_Drugs_data/dosesafe_formulary_v2.json` | Formulary location (relative to the repo). |
| `INTAKE_DATA_DIR` | `./data_local` | Records + audit folder (gitignored). |
| `OCR_MODEL`, `OLLAMA_URL` (must be localhost), `OCR_MAX_EDGE` 1400, `OCR_KEEP_ALIVE` 30m, `OCR_SESSION_TTL_S` 900, `OCR_TMP_DIR` ./tmp/ocr, `OCR_REVIEW_THRESHOLD` 0.7 | | OCR config. |
| `OCR_USERS_FILE`, `OCR_AUTH_IDLE_S` 900, `OCR_MAX_LOGIN_FAILURES` 5, `OCR_LOCKOUT_S` 60 | | Login gate. `OCR_FALLBACK=tesseract` is reserved, engine not in repo. |
`Config.override_min_chars` = 10 (not an env var). `DEMO_MODE` is read by both `Config.from_env()` and `intake/offline.py`.

## 3. Repo map
Top level:
- `api/` - FastAPI app (`main.py` create_app, `deps.py` lock/login/roles, `routers/`, `sessions.py`, `events.py`, `result_card.py`). `web/` - React app (`src/kiosk`, `src/staff`, `src/doctor`, `src/components`, `src/dosing`, `src/gallery`, `e2e/`).
- The Streamlit entry points (`main_app.py`, `intake_app.py`, `app.py`) and pages (`intake/ui/`) were removed in the rebuild; `docs/REBUILD_PLAN.md` maps every old feature to its new place.
- `README.md` - three-step flow, OCR, quiz, demo features. `CLAUDE.md` - commands, layout, hard rules for Claude sessions.
- `PROMPT_demo_features.md` - a prompt file used to ask for the demo features (not code).
- `.env.example`, `.gitignore` (ignores `.venv/`, `.env*`, `tmp/`, `fixtures/*.png`, `fixtures/*.expected.json`, `data/users.json`, `data_local/`), `requirements.txt`.
- `docs/` - `DOSING_LOGIC.md` (engine rules, Updates 2 and 3), `DOSING_DATA_ISSUES.md` (26 numbered data problems), `DEMO_SCRIPT.md`, `REBUILD_PLAN.md`, `DESIGN.md`, `UI_HIGHLIGHTS.md`, `screens/` (screenshots + demo.webm).
- `data/` - `intake_graph.json` (quiz), `red_flags.json` (10 draft rules), `body_regions.json` (54 regions), `doctors.json` (4 synthetic doctors), `formulary.json` (OCR seed list of 15 generic names + aliases; NOT the dosing formulary), `users.json` (logins, gitignored).
- `dosing/` - the dosage engine (below). `dosing/data/` - `med_synonyms.json`, `safety_map.json`, `plausibility.json`, `growth_reference.json`.
- `intake/` - quiz engine, red flags, summary, offline guard. `records/` - patient record schema/store. `ocr/` - local OCR module.
- `fixtures/` - OCR test images (rx_01..03, lab_01) and `fixtures/demo/demo_patient_{a,b,c}.json`.
- `scripts/` - CLIs listed in section 2. `tests/` - 29 test files + `snapshots/summary_adult_chest_pain.txt`.
- `data_local/` (gitignored runtime data: `records/PT-*.json`, `audit/dosing_audit.jsonl`), `tmp/ocr` (gitignored), `.venv/`, `.pytest_cache/`.
Not found in the repo folder: LICENSE, Dockerfile, CI config, setup/pyproject.

`dosing/` files: `engine.py` (evaluate entry point), `service.py` (record glue, confirm, history), `mapper.py` (quiz -> context), `context.py` (PatientContext + provenance), `rules.py` (rule selection), `calc.py` (dose arithmetic), `derived.py` (renal formulas, safe AST eval), `products.py` (round to products), `safety.py` (contraindications, pregnancy, renal, hepatic, warnings), `interactions.py`, `history.py` (History check), `meds.py` (synonym parsing), `ocr_meds.py` (confirmed scan meds), `formulary.py` (load/validate), `config.py`, `audit.py`, `audit_view.py`, `messages.py` (all user strings, English only), `demo.py`.
`intake/` files: `models.py` (pydantic graph), `engine.py` (pure flow), `conditions.py`, `redflags.py`, `session.py` (IntakeSession), `bodymap.py`, `summary.py` (doctor summary), `llm_summary.py`, `offline.py`, `doctors.py`, `demo.py`, `simulate.py`, `synthetic.py`.
UI code lives in `web/src/` (React) over `api/routers/` (FastAPI).
`records/`: `schema.py` (PatientRecord), `build.py` (answers -> record), `store.py` (JSON store), `vitals.py`. `ocr/`: `service.py` (`extract()`/`health()`), `prompt.py`, `schema.py`, `frequency.py`, `formulary.py` (fuzzy match to the 15 names), `postprocess.py`, `timeline.py`, `auth.py`, `ollama_client.py`, `imageprep.py`, `session.py`, `config.py`.

## 4. Quiz
- Data: `data/intake_graph.json`, version `0.1-draft`, start node `consent`, 73 nodes, validated by `intake/models.py` (pydantic, `extra=forbid`). Every node has text + options in en/hi/mr, a `next` object (ordered `rules` of `{if, goto}` + `default`), optional `socrates`, `shortLabel`, `redFlagRefs`, `source`, `sourceChecked`.
- Flow engine (`intake/engine.py`, pure): `next_node` = first matching rule else default; `recompute_path(graph, answers)` rebuilds the path from the answers so Back/edits stay consistent; answers are kept only for nodes on the final path. `validate_graph` checks targets, cycles, unreachable, never-ends, translations (`scripts/validate_graph.py`).
- Node types (count): single_choice 28, yes_no_unsure 16, multi_choice 12, body_map 6, scale_0_10 5, number 3, free_text 3. Sections: consent 1, basics 15, complaint 1, module 50, history 6.
- Condition language (`intake/conditions.py`, shared with red flags): `equals`, `in`, `gte`, `lte`, `all`, `any`, `not`, `answered`, `unanswered`, plus `regionsAny`, `regionsAll` for body maps.
- Answers: "Not sure" (`unsure`) is a real answer; skipped (`__skipped__`) is not an answer. Both continue the flow and both go to `dosingInputs.missing`. "unsure" never equals a concrete value. Consent must be explicit (`agree`/`decline`); decline deletes the record.
- Flow: consent -> basics (age_years, age_months, sex, pregnancy, preg_bleeding, weight_kg, allergies, allergy_other, meds_any, meds_list, kidney, liver, diabetes, hypertension, asthma) -> `chief_complaint` (fever, cough_breath, abdominal_pain, headache, chest_pain, other -> `other_text`) -> a complaint module (SOCRATES-style: site, onset, character, radiation, associated, course, severity, relief) with `danger_signs` -> history nodes (hx_fever, hx_cough, hx_abdomen, hx_head, hx_chest, hx_similar). Pregnancy is asked only for non-males aged 12-55.
- Body map: node type `body_map`, 54 region ids in `data/body_regions.json` (own polygons, no third-party art). `right`/`left` = the patient's own side. Answer `{regions, view, inputMode: map|list}` (+ `special`: tell_doctor / none / unsure). Tap position is resolved in Python (point-in-polygon with 4-unit slop); a checkbox list is always available. Offline component, no CDN.
- Red-flag rules (`data/red_flags.json`, evaluated after every answer by `intake/redflags.py`; all `urgent`, all `source: null`, `sourceChecked: false`, labelled "Draft rule, source check pending"):
  RF_CHEST_PAIN_RADIATION_SWEATING, RF_BREATHLESS_AT_REST, RF_SUDDEN_SEVERE_HEADACHE, RF_FEVER_NECK_STIFFNESS, RF_VOMITING_BLOOD_OR_BLACK_STOOL, RF_INFANT_FEVER_UNDER_3_MONTHS, RF_PREGNANCY_BLEEDING, RF_CONFUSION, RF_SEIZURE, RF_SUDDEN_WEAKNESS_OR_SPEECH.
- Answers -> record: `IntakeSession` (`intake/session.py`; token `PT-` + 6 chars) holds answers, re-computes the path and red flags after each answer, and `to_record()` calls `records/build.py`. That builds `PatientRecord` (`records/schema.py`): `consent`, `dosingInputs` (age, weight, sex, pregnancy, allergies, renal/hepatic/diabetes/hypertension/asthma, currentMeds, `missing`), `complaint`, `socrates` (site/radiation objects + AnswerLine lists), `history`, raw `answers`, `redFlags` (rule id, severity, messages, `draft`, `triggeredBy`), `timeline` (confirmed OCR scans), `assignedDoctor`, `vitals` (staff), `doctorNotes`, `doctorEdits`, `visitHistory`, `dosingChecks`. Saved as `data_local/records/PT-XXXXXX.json`. No name/contact field exists. Quiz answers are immutable; doctor entries live in separate fields. After the quiz the patient picks a doctor from `data/doctors.json` (synthetic; stored as `assignedDoctor`).
- Doctor summary (`intake/summary.py`): deterministic text, same record gives same text (snapshot test). Edits tracked per field. Optional AI paragraph sees a number-free fact sheet; output with digits, dose words or diagnostic language is discarded.
- Translations: all hi/mr text (nodes, red-flag patient messages, UI strings, region labels, doctor specialties) is "machine-drafted, needs native review". Not reviewed.

## 5. Dosing engine (`dosing/`, ENGINE_VERSION 0.1.0)
Data flow:
`PatientRecord` -> `service.evaluate_for_record` -> `mapper.map_record` (quiz answers -> `PatientContext`, every value has provenance: `patient_reported`, `doctor_entered`, `doctor_confirmed`, `derived`, `unknown`) -> `engine.evaluate(Request)` (applies History-check answers, confirmations and doctor inputs, then selects rules, solves, checks safety/interactions, applies overrides) -> result dict -> `audit.write` (every evaluation + each override) -> doctor may `service.confirm` (appends `DosingCheck` to `PatientRecord.dosingChecks`, writes audit).
`Request` fields: drug, context, indication, doctor_inputs, confirmed, visit_drugs, selected_rule_id, form, route, show_all_rules, override_reason, override_category, doctor_id, history.

Statuses (priority): `blocked` > `refused` > `needs_input` > `ok`.
- `ok`: dose computed. `final` is true only if ok, a number was computed, and weight (plus creatinine when a renal measure was used) is doctor-entered or doctor-confirmed (`pending_confirmations` lists what is not).
- `needs_input`: a missing fact, listed with a reason (`needs_input[]`).
- `blocked`: an unoverridden hard stop (`blocks[]`).
- `refused`: unknown drug, no rule, UNVERIFIED rule while `DOSING_ALLOW_UNVERIFIED` is off, or incomplete rule.
- Dose fields (`dose_mg`, `product`, `volume_ml`, `units`, `daily_total_mg`) are blanked unless status is `ok`; `dose_range_mg` also blanked on blocked/refused.
- Result keys: status, drug, indication, selected_rule_id, suggested_rule_id, alternatives, dose_mg, dose_range_mg, product, product_options, volume_ml, units, interval_h, doses_per_day, daily_total_mg, daily_max_mg, binding_cap, duration, plan, text_regimen, computed, calculation_steps, warnings, label_warnings, blocks, needs_input, refused_reasons, interactions, overrides, provenance, sources, data_status, final, pending_confirmations, acknowledge_items, boundary_overlap, indications, engine_version, formulary_version, banner, demo, demo_banner.

Quiz -> context (`mapper.py`; unknown = not asked / skipped / "not sure", never "no"; whether a node was asked comes from `recompute_path`): age (years 0 uses months; otherwise years x 12 with an 11-month window; a rule boundary inside the window gives `needs_input` for `age_exact_days`), sex (`other`/skipped: doctor picks `sex_for_formula`), pregnancy (unsure -> `possible`; derived `no` only if the quiz legitimately skipped the question), weight (patient_reported + draft plausibility warning), allergy classes (penicillins, sulfa, nsaids), free-text allergy/meds normalised through `med_synonyms.json` (unmatched -> "unparsed: doctor to review"), kidney/liver/diabetes/hypertension/asthma, ulcer/alcohol/stones (from `hx_abdomen`), gi_bleed (from `danger_signs`), heart_disease/smoking (from `hx_chest`/`hx_cough`), red flags (read-only). Doctor-only, never defaulted: drug, indication, height, creatinine, breastfeeding, Child-Pugh, QT history, G6PD, dialysis, pregnancy weeks/trimester, form, doses per day, mg/kg/day.

Rule selection (`rules.py`):
- Indication key = label text before the first `,` or `(`, lower case; `any`/`all indications` rules match every indication; "Show every rule" lists all rules fitting the patient.
- Age: min inclusive, max inclusive through the completed unit (`max_age_years: 17` = up to 17 y 11 m). Weight: min inclusive, max exclusive. Empty population `{}` = paediatric (<18) when weight-based, else applies with a warning.
- Adult rule = `min_age_years >= 18`; adult rules supersede open-ended weight-based rules for adults. Drug `adult_switch` (amoxicillin-clavulanate, 40 kg) applies the adult rule at or above that weight.
- Identical dose content from different sources is merged (others listed as corroborating). More than one live rule: all returned, first VERIFIED (else SECONDARY) is `suggested_rule_id`, doctor must pick `selected_rule_id`.
- Boundary overlap (patient age equals shared bound, e.g. cetirizine at 6 y or 12 y): all matches returned in `alternatives`/`boundary_overlap`, default = lowest daily total then earlier rule, with a warning.
- Rule `options`: dict options become pseudo-rules (`drug#3.0`); free-text options are shown, never computed. Rule with no `route` = oral. Rule ids are `drug#index` (reordering the file changes them).

Calculation (`calc.py`, `derived.py`): dose types supported = fixed, fixed_daily, mg_per_kg_per_dose, mg_per_kg_per_day, weight_band, titration, duration_only. Formulas are evaluated from formulary `formulas` strings by a whitelisted AST evaluator (`safe_eval`).
- Caps: per dose, per day, per kg per day, per course, max doses/day, `range_mg`, hepatic max, and formulary `defaults.<drug>_child` for children when the rule is silent. The binding cap is reported (`binding_cap`). Products are never rounded above a bound cap.
- Rounding (`products.py`): liquids to `DOSING_ML_STEP` (0.5 mL) with delivered mg reported and half a step of slack against the range; tablets whole only (no scored flag exists in the data); solid forms preferred when in range. Amoxicillin-clavulanate is computed on the amoxicillin component and matched to products by ratio key (e.g. `200/28.5`).
- Renal: measure named by the rule is used. `CrCl`/`GFR` = Cockcroft-Gault; `eGFR` = CKD-EPI 2021 (adults) or bedside Schwartz (1-16 y). Renal action text changes the dose only for adult fixed rules and only if it parses as "N mg every H h / once daily"; otherwise a warning. Creatinine is needed (`needs_input`) when kidney disease is yes/unsure/unknown and the drug has numeric renal bands. Cockcroft-Gault uses actual weight.
- Hepatic: Child-Pugh score or class (doctor-only); hepatic max applies as a cap; text-only otherwise. No class-to-score mapping exists.
- Pregnancy/lactation: pregnancy `yes` or `possible` + a pregnancy-contraindication text (regex in `safety_map.json`) = block (overridable); otherwise a warning. Pregnancy unknown + contraindication = `needs_input`. Lactation is a doctor-entered warning. Sex-for-formula and weeks/trimester are doctor-entered.
- Blocks (overridable): allergy class, free-text allergy hitting the drug, contraindication/block_rule predicate true, pregnancy contraindication, age/weight outside every rule, renal band "Contraindicated / Do not use / Do not start", blocking interaction (severity `block`/`contraindicated`), off-label child (`override_rules`).
- Warnings: possible pregnancy text, lactation, hepatic/renal notes, label warnings (`safety_map.json` triggers), non-blocking interactions, unchecked free-text items ("Not machine-checked, doctor to confirm"), unconfirmed weight/creatinine, implausible weight (never corrected).
- Heart disease: the broad quiz answer no longer blocks. Each contraindication mentioning heart failure/IHD becomes its own yes/no/unsure question `q_<hash>` quoting the formulary text exactly.
- Unchecked free-text contraindications stay warnings; the result lists them in `acknowledge_items` and `service.can_confirm(res, acknowledged)` stays false until the doctor ticks "I have checked these".

Interactions (`interactions.py`): top-level `interactions[]` (41, structured severity) plus each drug's free-text interactions (severity "unspecified"). Targets = current meds (self-reported or doctor-typed, normalised), other drugs in the same visit (`visit_drugs`), doctor-confirmed scanned meds (`ocr_meds.py`, provenance `ocr_doctor_confirmed`), and context flags. Duplicate therapy by `duplicate_class`. Unrecognised medicine names are warned, never dropped. Qualifiers in `b` fields are ignored by matching.

Overrides: only for blocks with `overridable`. Needs `override_category` in {benefit_outweighs_risk, patient_tolerates, no_alternative, other}, a written reason of at least 10 characters, and a doctor id. A valid override turns each overridable block into a visible, logged warning and lists it in `overrides[]`; it also lets the engine show rules for an off-label age/weight (`warn_offlabel`). Stored in the audit entry, `PatientRecord.dosingChecks` and the doctor summary ("Dosing record").

History check (`history.py`, `service.save_history`): lists the yes/no/unsure facts the selected drug depends on (allergy classes, ulcer, GI bleed, alcohol, asthma, diabetes, hypertension, kidney, liver, pregnancy, breastfeeding, QT, heart disease and every contraindication question). The panel shows only unknown ones plus a "None of these apply" button (sets all to no). Saved to `PatientRecord.visitHistory` (provenance `doctor_confirmed`, applies to every drug in the visit, audit event `history`). "Unsure" always counts as unknown (pregnancy: `possible`).

Audit (`audit.py`): append-only JSONL at `<INTAKE_DATA_DIR>/audit/dosing_audit.jsonl` (default `data_local/audit/`). Events: `evaluate`, `confirm`, `override`, `history`. Each line holds ts, event, token, doctor_id, drug, indication, status, override_reason, inputs, provenance, full result, engine_version, formulary_version, `prev`, `hash`. Hash = SHA-256 of the sorted-key JSON of the entry without `hash`; first `prev` = 64 zeros; each write is fsync-ed. `verify()` recomputes the chain ("Chain verified"/"Chain broken" in the viewer). `rewrite()` is only for `scripts/reset_demo_data.py`.

## 6. Data
Dosing formulary: NOT in the repo. `dosing/config.py` loads `../Final_Drugs_data/dosesafe_formulary_v2.json` (268,766 bytes), next to a "DoseSafe formulary gap fill.md" and a "Drug_Reference_15_Medicines_Source_Limited.pdf" (neither read). Never edit it (CLAUDE.md). Tests need it at that path (they passed with it there).
Top-level keys: `meta`, `sources`, `formulas`, `defaults`, `drugs`, `interactions` (`dosing/formulary.py` rejects any other key).
- `meta`: name "DoseSafe 15-drug formulary", version `0.2.0`, generated 2026-11-03, status_key (VERIFIED = read in source text; SECONDARY = reputable summary; UNVERIFIED = do not ship), disclaimer, rule_hierarchy (Indian guideline > WHO > FDA label > UK SmPC/MSF), units, changelog.
- `sources`: 67 entries (ids S1.. plus AAPD, HPRA), each with name/url. Rule `source` text is parsed into ids/sections.
- `formulas`: cockcroft_gault, ckd_epi_2021, bedside_schwartz, mosteller_bsa, ideal_body_weight, adjusted_body_weight (`factor_default`), with population and status.
- `defaults`: `paracetamol_child`, `ibuprofen_child`, and text notes (amoxicillin_child "doctor picks", ciprofloxacin_child, ondansetron_child, missing_input "refuse", kiosk_inputs "unverified until doctor confirms").
- `drugs[]` keys: id, generic, class, atc, rxcui, forms_india, dose_rules, renal_rules, hepatic_rules, contraindications, block_rules, warnings, pregnancy(+_additional), lactation(+_additional), food, interactions, duplicate_class, qt_risk, dose_basis, adult_switch, override_rules, gaps, verified, reviewed_by, review_date, jan_aushadhi, nppa_ceiling_price, etc. A dose rule has indication, population (age/weight bounds), dose_type, the numeric fields, caps, duration, `source`, `status`, optional `note`/`conflict`.
- 134 dose rules: 108 VERIFIED, 23 SECONDARY, 3 UNVERIFIED. All 15 drugs `verified: false`.
The 15 drugs (id: dose rules): paracetamol 8, amoxicillin 13, amoxicillin_clavulanate 7, azithromycin 12 (qt_risk), metronidazole 17, pantoprazole 4, diclofenac 9, ibuprofen 5, cetirizine 6, metformin 6, amlodipine 5, telmisartan 3, doxycycline 16, ondansetron 13 (qt_risk), ciprofloxacin 10 (qt_risk).
Engine-side data (`dosing/data/`, all DRAFT, a clinician/pharmacist should review):
- `med_synonyms.json` (`_note` + `entries`: names, labels, generic, drug_id, kind). No fuzzy matching. Brand/class mapping is engine-side, not formulary content.
- `safety_map.json` (`ci_map` 30 regex->predicate entries, `pregnancy_block_regex`, `lactation_against_regex`, `renal_actions`, `hepatic_actions`, `warning_triggers`). Thresholds come from the formulary text via regex groups. Unmapped text still shows as "doctor to confirm". Predicate kind `question` = a History-check item.
- `plausibility.json` - labelled DRAFT, NOT CITED weight ranges by age; used only while the growth file is empty.
- `growth_reference.json` - status "needs data": structure only, empty `rows` for WHO CGS 0-5 y, WHO 2007 5-10 y, IAP 2015 5-18 y, adult limits (boys/girls). Row format `{age_months, minus3sd_kg, plus3sd_kg}`. The check flags about -3 SD to +3 SD and never corrects weight.
Other data: `data/formulary.json` (OCR name seed, 15 generics + aliases), `data/doctors.json` (dr_general, dr_heart, dr_child, dr_women; synthetic), `fixtures/demo/demo_patient_{a,b,c}.json`.

## 7. UI (FastAPI + React; Streamlit retired 2026-11-04)
One server (`scripts/run_server.py`, one uvicorn worker, 0.0.0.0:8000) serves `/api` and the built React app. Details: `docs/REBUILD_PLAN.md` (parity checklist, permissions matrix, API list), `docs/DESIGN.md` (tokens, review log), `docs/UI_HIGHLIGHTS.md`.
- **Kiosk `/kiosk`** (no login; a per-session `X-Kiosk-Key` opens only its own token): language -> consent -> one question per screen (tiles, keypad, 0-10, multi-choice with exclusive none, free text, SVG body map with list alternative) with Back / Not sure / Skip -> review and edit -> choose doctor -> token slip (queue number, room, floor-line colour) -> auto reset. Listen again only with a local speech voice; Call staff; larger text and high contrast; 90 s idle reset. Sessions rebuild from the saved record after a restart. Patients see only red-flag patient messages.
- **Staff `/staff`** (staff or doctor login): live board via SSE (10 s polling fallback), urgent red flags pinned with draft label and triggering answers, help-request banner, table with search/sort/filters and bulk doctor assignment, patient panel (answers in en/hi/mr, vitals with server bounds, doctor reassignment, scan upload for the doctor to confirm). No dosing.
- **Doctor `/doctor`** (doctor login): my queue; patient workspace (Summary with edit tracking and body diagrams, Vitals, Timeline with scan confirmation, Notes, Dosage check, Dosing record); Audit log (cursor-paged, chain seal, export, no edit/delete); Load demo patient (DEMO_MODE).
- **Dosage check** mirrors the old panel and result card: drug combobox, indication, optional form/route/visit drugs/every rule, History check, weight confirmation, Run; result headers per status, needs_input checklist with Update and recompute, override form (category + 10 chars, server-enforced, audit-logged), dose ruler for ok only, Confirm gated by the server's canConfirm (server-cached result only).
- **Auth**: `ocr/auth.py` users, lockout after 5 failures, idle timeout; in-memory sessions with an httpOnly SameSite=Strict cookie; every mutating call needs `X-Requested-With: medikiosk`.
- **Offline badge**: `GET /api/system/offline-status` (same `intake/offline.py` status and headline).

## 8. Hard rules (from CLAUDE.md and docs; do not break)
- No LLM, network or randomness in `dosing/`. Pure functions; same input gives byte-identical output.
- No invented clinical values: every clinical number comes from the formulary JSON. Never hard-code doses, limits, thresholds or interactions. Missing field -> refuse or `needs_input`; never guess.
- Refuse by default: unknown drug, no rule, UNVERIFIED rule (unless `DOSING_ALLOW_UNVERIFIED`/demo), incomplete rule.
- Never edit the formulary JSON, `data/intake_graph.json` or the red-flag rules; log data problems in `docs/DOSING_DATA_ISSUES.md`.
- Nothing is marked clinically verified. Keep the "Prototype data, not clinically verified" banner. Fill red-flag `source`/`sourceChecked` only after a person checks the cited document.
- "Not sure" and "not asked" are unknown, never "no".
- Hard blocks are overridable only with a category plus a written reason of 10+ characters, and the override is audit-logged.
- Quiz answers are immutable; doctor entries are stored separately (`doctorEdits`, `visitHistory`, `dosingChecks`). Patients never see dosing output.
- Synthetic data only; local-only network (localhost). Tests derive expected values from the formulary JSON, not typed-in numbers (except arithmetic tests). Engine strings live in `dosing/messages.py`. Match surrounding style; no new frameworks.

## 9. Current state
Tests: 829 Python (domain + `tests/api/`: role matrix over every route, CSRF, lockout, idle, write-lock concurrency, SSE, kiosk parity with IntakeSession, restart rebuild, idempotent finish, byte-identical evaluate, override and confirm rules, audit paging and tampering, error states, OFFLINE_STRICT), 17 Vitest (no dose number unless ok, ruler only for ok, components), 16 Playwright (full Hindi kiosk flow, three demo scenarios, live staff board, axe, offline, four viewports, Ollama down). The 55 Streamlit AppTest functions were removed; see `docs/REBUILD_PLAN.md`.
Done: quiz graph + 10 draft red flags + body map; record store; doctor summary; staff board; doctor login; local OCR with doctor confirmation; dosing engine for 15 drugs (rule selection, caps, rounding, renal, hepatic, pregnancy, interactions, History check, overrides, hash-chained audit); result card; audit viewer; offline badge + strict guard; demo patients + reset script; demo script.
Not done / not found: verified clinical data; growth tables; Hindi/Marathi for dosing messages (`messages.py` is English only); native review of any hi/mr text; sources for the 10 red-flag rules; IBW/ABW selection rule; G6PD logic (field shown only); CrCl for children and ages 16-18; REST API for OCR (functions are framework-free only); formulary inside the repo; deployment/packaging, CI, license.
Known issues (`docs/DOSING_DATA_ISSUES.md`, 26 items; formulary not modified):
- Rule ids are `drug#index` (reordering the file changes them); `population: {}` has no stated meaning; `max_age_*` semantics conflict (cetirizine/amoxicillin-clavulanate exclusive vs metronidazole inclusive); weight-bound gaps (ibuprofen 20-29 kg; doxycycline 45/45.5).
- Free-text indications overlap (paracetamol adult 4+ rules; amoxicillin WHO vs ICMR vs US label). 8 cetirizine boundary pairs at 6 y and 12 y; 27 open-ended overlaps handled by adult-supersedes or doctor choice.
- Incomplete rules refused: doxycycline rule 14 (no value), ondansetron rule 7 (no `mg_per_kg`); cap-only rules need a doctor-entered mg/kg/day; amoxicillin WHO bands stop at 20 kg.
- Pantoprazole lists only an injection form, so oral doses return `needs_input`; amoxicillin-clavulanate products named in rules are missing from `forms_india`; no scored-tablet flag.
- Safety text is free text, mapped by `safety_map.json`; unmapped items (dehydration, dengue, past cholestatic jaundice, quinolone hypersensitivity) show as "doctor to confirm". Interaction `b` qualifiers ignored; one mixed-status interaction treated as UNVERIFIED; no Child-Pugh class-to-score mapping; ciprofloxacin has no band below CrCl 5; cetirizine renal rows conflict; `defaults` keys named differently from rule keys; asthma/diabetes warnings exist only for some NSAIDs; no G6PD text.
- 3 UNVERIFIED rules (e.g. cetirizine 0-2) mostly merged away; engine-side tables (plausibility, synonyms) are unsourced drafts.
- Runtime observations: `data_local/audit/dosing_audit.jsonl` is already ~9.7 MB (viewer speed with large logs not tested); `fixtures/*.png` are gitignored so `make_fixtures.py` regenerates them; the formulary path is outside the repo, so a fresh clone without `../Final_Drugs_data/` cannot run dosing or most dosing tests.
Open clinician questions:
1. Wording of the NSAID heart question (diclofenac: congestive heart failure NYHA II-IV, IHD, peripheral arterial disease; ibuprofen: severe renal, hepatic or heart failure, a compound text). Should stroke/cerebrovascular disease be added? It appears nowhere in the formulary; any addition must be a reviewed formulary change with source, not a code change.
2. Cetirizine at 6 y and 12 y: which rule should win? (Currently lower dose / earlier rule by default; doctor may pick.)
3. Which free-text contraindications should hard-block instead of warn.
4. Growth tables to supply: WHO CGS weight-for-age 0-5 y, WHO 2007 5-10 y, IAP 2015 5-18 y, a cited adult range.
5. Reviewed list of override reasons and a periodic override audit (current rule is a prototype).
6. Sources for the 10 red-flag rules (WHO IMCI, ICMR STW suggested in README); severities are placeholders.
7. Amoxicillin dose choice (WHO 80-90 vs ICMR 30-40 mg/kg/day): doctor picks today.
8. Native review of all hi/mr text.

## 10. Next steps and how to continue
Suggested order (not from the repo; these follow its open items): (1) copy the formulary into the repo or make the path configurable in the README/CI; (2) hi/mr for `dosing/messages.py`; (3) get clinician answers to the open questions above; (4) fill `growth_reference.json` from supplied tables; (5) native review of translations; (6) source the red-flag rules; (7) re-run the demo end to end with `OFFLINE_STRICT=1`.

Where to add things:
- Add a drug: (a) add it to the formulary JSON (engine is read-only on that file) and run `pytest tests/test_dosing_data.py` (fails on any unsupported `dose_type`, field, form or strength shape); (b) add a `dosing/data/med_synonyms.json` entry with `drug_id` and labels including its `duplicate_class` (and `qt-prolonging` if `qt_risk`); (c) add `dosing/data/safety_map.json` `ci_map` entries for its contraindication / block_rule texts; (d) add tests for its rules; (e) add its generic name to `data/formulary.json` if OCR should recognise it. (`docs/DOSING_LOGIC.md` "Adding a drug").
- Add or change a rule: change the formulary JSON (not code); rule selection is in `dosing/rules.py`, arithmetic in `dosing/calc.py`, safety predicates in `dosing/safety.py` + `safety_map.json`. Run `scripts/list_boundary_overlaps.py`, then record any new data problem in `docs/DOSING_DATA_ISSUES.md`. A new `dose_type` needs a case in `calc.py` and the `SUPPORTED_DOSE_TYPES` set in `dosing/formulary.py`.
- Add a quiz question or red-flag rule: edit `data/intake_graph.json` / `data/red_flags.json` only when asked (CLAUDE.md forbids unrequested edits), give en/hi/mr text, run `scripts/validate_graph.py` and the quiz tests. Map new facts into the engine in `dosing/mapper.py`.
- Add a demo fixture: create `fixtures/demo/demo_patient_<x>.json` with `key`, `displayName`, `title`, `token`, `synthetic: true`, `answers` (by graph node id), `check` (`drug`, `indication`, `selected_rule_id`, `history`: e.g. `none_apply`) and `runs` (`label`, optional `confirmed`/`doctor_inputs`/override fields, `expect_status`). Register it in `dosing/demo.py`; expected statuses are checked by `tests/test_dosing_scenarios.py` and `tests/test_demo_features.py`. Take expected numbers from `scripts/dosing_demo.py` output, not from memory, and update `docs/DEMO_SCRIPT.md`.
- Add an engine message: `dosing/messages.py` (add hi/mr there when translations are available).
- Add a kiosk UI string: `web/src/i18n/kiosk.json` (en/hi/mr, hi/mr machine-drafted); staff/doctor screens are English.
- Before finishing any change: `.venv/bin/python -m pytest -q`; keep the banner; do not mark anything verified.

## 11. Patient identity and kiosk scan (branch `feat/patient-identity-ocr`, 2026-11-04)
Plan and decisions: `docs/IDENTITY_OCR_PLAN.md`. Storage and what is not claimed: `docs/SECURITY.md`.
- **Kiosk flow**: language -> Step 1 identify (method tiles, number pad, PIN, consent) -> Step 2 scan papers -> Step 3 the existing quiz, doctor choice, token slip. A step indicator shows 1/2/3. "Ask staff" makes a walk-in; "No thanks" at consent continues anonymously (no identifier, no scans stored). Idle reset is 50 s + a visible 10 s countdown.
- **Identity**: mobile (`+91`, 10 digits starting 6-9) or ABHA (14 digits, format only) plus a 4-digit PIN. No SMS offline, so no OTP (`api/identity_provider.py`: `PinProvider`; `OtpProvider` is a raising stub). Fernet-encrypted identifier, HMAC lookup hash, argon2id peppered PIN (`records/identity.py`), patient files in `data_local/patients/`, key in `IDENTITY_MASTER_KEY` or `data_local/identity.key`. 5 wrong PINs lock 10 minutes (persisted); per-device and per-number rate limits.
- **API**: `POST /api/kiosk/identify|register|login|walk-in`, `POST /api/kiosk/sessions/{token}/bind|end`, scans under `/api/kiosk/sessions/{token}/scans` (upload, poll `GET /{id}`, PATCH, `confirm`, DELETE, `image`), staff `/api/staff/patients` (lookup, `reset-pin`, `walk-in-complete`), doctor `/api/doctor/visits/{token}/scans|previous|scans/{id}/use-as-current-medicines`. The identity token travels in `X-Kiosk-Identity` and opens only kiosk routes of its own visit.
- **Scan**: existing `ocr.service.extract` (now with an optional streaming `progress` callback and role `kiosk`) on one background worker (`api/scan_jobs.py`); blur/dark pictures are refused before OCR; status lives in `PatientRecord.kioskScans` (unverified). Images in `data_local/scans/`. `KIOSK_SCAN_KEEP_IMAGE=0` deletes the picture on confirm.
- **Audit**: `records/identity_audit.py` appends identity/consent/scan/PIN-reset events to the same hash-chained file (`dosing/` untouched).
- **Staff/doctor UI**: board shows masked number, new/returning, papers, honest status; `/staff/people` lookup, Reset PIN, Complete walk-in; the doctor Timeline has a "Patient papers" panel (images, unverified label, Use as current medicines, previous visits).
- **Tests**: `tests/api/test_api_identity.py`, `tests/api/test_api_scans.py` (fake OCR backend); `web/src/kiosk/identity/validation.test.ts`; Playwright `web/e2e/identity.spec.ts`, `identity-desk.spec.ts`. `scripts/e2e_server.py` uses a fake reader for the kiosk scan step unless `--real-ocr`.
