# Rebuild plan: Streamlit to FastAPI + React

Source of truth for behaviour: the Streamlit pages in `intake/ui/` and the domain packages. Baseline before the rebuild: **844 Python tests pass** (the hand-off says 838; the last commit added 6).

Order of work: the hackathon is on 3-4 Nov 2026, so the work followed the prompt's **demo slice** (Phase 1, then the doctor Dosage check with ruler, audit chain and demo loader, then the kiosk, then the staff board), then hardening, polish, and Streamlit retirement (Phase 7).

## (a) Parity checklist

Legend: [x] done and checked in the new app, [ ] not carried over on purpose (reason given). "Where" is the new home.

### Sign in and gate (`signin.py`, `gate.py`, `ocr/auth.py`)
- [x] Username/password sign in, roles staff and doctor -> `/staff/login`, `/doctor/login` (one shared `LoginPage`), `POST /api/auth/login`
- [x] Lockout after 5 failures (per username, `OCR_LOCKOUT_S`) -> reuses `ocr.auth.Authenticator` (one per process)
- [x] Idle logout after `OCR_AUTH_IDLE_S`, with "Logged out after inactivity." -> server session expiry, 401 with `reason: idle`, login page notice
- [x] "No users exist yet" message -> login page shows the `create_user.py` command when `GET /api/auth/me` reports `usersExist: false`
- [x] Sign out -> header user menu, `POST /api/auth/logout`
- [x] `can_edit` = doctor only -> `require_role("doctor")` dependency on every doctor-only route

### Offline badge (`offline_badge.py`, `intake/offline.py`)
- [x] Pill with the headline from `offline.headline()` on every staff/doctor page -> `OfflineBadge` in both shells
- [ ] Badge on the patient kiosk: deliberately not shown (open question 3)
- [x] Network details: allowed target and reachability, local services, probe host/timeout/interval, strict-mode text -> badge popover, `GET /api/system/offline-status`
- [x] 30 s refresh without blocking -> TanStack Query `refetchInterval` from `probeIntervalS`
- [x] `OFFLINE_STRICT=1` installs the guard -> `create_app()` calls `offline.install_if_strict()`

### Patient kiosk (`patient.py`, `bodymap_input.py`, `strings.py`)
- [x] Language toggle en/hi/mr always visible -> language screen + header "Change language" (`PUT .../language`)
- [x] Explicit consent agree/decline; decline deletes the record and shows the declined text -> consent screen, `POST .../consent`
- [x] Red-flag `patientMessage` only (first fired rule), no detail -> calm card with icon above the question (`screen.redFlagMessage`)
- [x] One question per screen; single_choice and yes_no_unsure tiles; multi_choice with Next and `none` exclusive; number with min/max; scale 0-10; free text; body map -> `QuestionScreen` with one input per type
- [x] Back (previous node on the current path) -> `POST .../back`
- [x] Not sure (answer) and Skip (not an answer) on every non-consent question -> secondary row; for yes_no_unsure/body_map "Not sure" sends the node's own `unsure` option
- [x] Body map: tap map + list, front/back, max selections warning, Clear, specials (not sure / tell doctor / none), answer built by `bodymap.make_answer` -> `BodyMap`; server builds the answer from `{regions, view, inputMode}` or `{special}`
- [x] Progress bar -> calm bar from `session.progress()` (no "x of y" text)
- [x] Review: every answer with Change; "Everything is correct - finish" -> review screen, `GET .../review`, edit goes to `GET ...?node=`
- [x] Finish keeps staff-entered vitals and clears doctor edits -> `POST .../finish` (server merges prior vitals, scans and timeline)
- [x] Choose doctor or "Any available doctor" -> doctor screen, `POST .../doctor`
- [x] Done screen "Thank you. Please wait..." + your doctor -> token slip (new) + "Done" + 60 s auto-reset
- [x] Demo chest-pain patient button on the consent screen -> moved off the kiosk (no dev text on a patient tablet): DEMO_MODE staff board button "Add synthetic chest-pain patient" (`POST /api/demo/kiosk-patient`)
- [x] Optional OCR scan stage before the quiz (signed-in staff/doctor only) -> moved to the staff desk and doctor timeline (product decision 1)

### Staff board (`staff.py`)
- [x] Records sorted: most urgent flags, most flags, then oldest update -> `GET /api/patients` (server sorts; urgent first)
- [x] Per patient: token, status, complaint, chosen doctor or "no doctor chosen" -> board table columns
- [x] Red flags with severity, staff message, rule id, draft label, triggering answers (English labels) -> pinned urgent rows + patient panel
- [x] "No red flags." / missing safety basics -> patient panel
- [x] Vitals form (9 measured fields + notes), bounds, systolic > diastolic, "Vitals saved. The doctor can see them now." -> `VitalsForm`, `PUT /api/patients/{token}/vitals` (422 with field errors)
- [x] Abnormal adult-range warning (draft thresholds) -> `abnormal` returned in the patient view
- [x] Auto refresh every 5 s -> SSE `/api/events` with 10 s polling fallback
- [x] Caption "Red flags come from draft rules..." -> board header text

### Doctor summary (`doctor.py`, `intake/summary.py`)
- [x] Patient picker; my patients first (linked login), then flags, then updated -> "My queue" (`GET /api/patients?mine=1` ordering done on the server)
- [x] Read-only notice for staff -> staff never reach `/doctor` routes (403); staff panel is its own read-only view
- [x] "AI drafts, the doctor decides. Red flags come from DRAFT rules..." -> summary section header text
- [x] Demo loader box -> sidebar "Load demo patient" (DEMO_MODE + doctor)
- [x] Intake duration and fields captured -> summary header facts
- [x] Clinical overview: token, status, complaint, assigned doctor, red-flag count -> patient header
- [x] Patient basics (age, sex, reported weight, pregnancy, allergies, medicines, conditions incl. not sure, missing list) -> Summary section top block
- [x] Vitals with abnormal marks, BMI, child note, reported vs measured weight warning, recorded by/at -> Vitals section (`GET /api/patients/{token}` returns `bmi`, `abnormal`, `weightMismatch`)
- [x] Attached OCR records with items table, edited/as-read tag, confirmed by -> Timeline section
- [x] Dosing record: History check by whom; each confirmed check line; OVERRIDE lines -> Dosing record section
- [x] Doctor notes with Save notes -> Notes section, `PUT .../notes`
- [x] Editable intake summary with edit tracking ("edited", Original: ...), red flags read-only, missing markers -> Summary section, `GET/PATCH .../summary`
- [x] Summary language (en/hi/mr) -> answer-language toggle (`?lang=`)
- [x] Body diagrams, site red, radiation orange -> small SVGs drawn from `GET /api/intake/body-regions` + `socrates.site/radiation`
- [ ] Attach timeline JSON paste: dropped, superseded by scan upload + doctor confirmation (open question 4)
- [x] Short paragraph: template (deterministic) and optional local-AI draft -> template paragraph shown; local-AI draft kept behind `POST .../summary/paragraph` (doctor, needs Ollama, 503 when down)

### Dosage check (`dosage.py`, `dosing_panel.py`, `result_card.py`)
- [x] Banner "Prototype data, not clinically verified" (+ "UNVERIFIED rules are computed" when allowed); red DEMO bar when demo mode -> always-visible banner in the Dosage check section; DEMO bar from `result.demo`
- [x] "Decision support only..." caption -> section intro
- [x] Drug select (generic names), indication select -> searchable combobox + select (`GET /api/dosing/drugs`)
- [x] Show every rule; other drugs this visit -> checkboxes / multi-select
- [x] History check: only unknown items, labels, required marker, exact formulary question, "Already known" line, "None of these apply", Save; "Nothing unknown for this drug." -> `HistoryCheck`, `POST /api/dosing/history-items`, `POST /api/patients/{token}/history`
- [x] Patient context with provenance chips -> context grid from `history-items` response `context`
- [x] Current medicines used for interactions, with source tags and unparsed lines -> `context.medicines`
- [x] Doctor-entered inputs (weight, confirm weight, height, creatinine, pregnancy override, weeks, trimester, Child-Pugh class/score, G6PD, medicines text, form, doses/day, mg/kg/day) -> "Doctor-entered inputs" disclosure + weight confirmation checkbox before Run
- [x] Run dosage check -> `POST /api/dosing/evaluate`
- [x] Result card header per status, reason, responsible line, sources (id, name, link text) -> `ResultCard` from `card`
- [x] needs_input checklist with per-field input kinds (rule picker, num, tri, choice, text, elsewhere) and Update and recompute -> `MissingChecklist` (`card.missing[].kind` from `field_kind`)
- [x] Override form: category + reason (10+ chars), "Record override and show dose" -> `OverrideForm`; server validates with `override_error`
- [x] Red "Override recorded" line(s) -> `card.overrides`
- [x] Blocks list, needs-input list -> result details
- [x] Dose metric, interval, daily total, daily max, binding cap -> dose block + dose ruler (ok only)
- [x] Titration plan, free-text regimen, duration (hidden on blocked/refused) -> dose block
- [x] "Provisional: confirm ..." -> pending confirmations line
- [x] Alternatives side by side with "Use this rule" -> alternatives list
- [x] Calculation steps expander (hidden text on blocked/refused) -> numbered disclosure
- [x] Warnings, interactions, label warnings, sources -> lists/disclosures
- [x] Acknowledge items + "I have checked these" -> checkbox; Confirm disabled until server says `canConfirm`
- [x] Confirm and save to record -> `POST /api/dosing/confirm` (server-cached result only)

### Audit log (`audit_log.py`, `audit_view.py`)
- [x] Doctor only -> `require_role("doctor")`
- [x] Chain verified / broken -> `GET /api/audit/verify` (+ first bad index), seal
- [x] Newest first table, filters (patient, drug, action, from, to) -> infinite table, `GET /api/audit`
- [x] Row expander (inputs, provenance, steps, warnings, interactions, blocks, sources, override category/reason/block, hash) -> row expander from `audit_view.detail`
- [x] Export shown rows JSON/CSV -> `GET /api/audit/export`
- [x] No edit/delete -> no such endpoint exists

### Demo (`demo_loader.py`, `dosing/demo.py`)
- [x] DEMO_MODE + doctor only -> `GET /api/demo/fixtures`, `POST /api/demo/load/{key}` (404 when DEMO_MODE is off)
- [x] Load replays fixture answers through the real session, saves, selects -> same `demo.record(key)`; UI navigates to the patient's Dosage check

### Not carried over
- `app.py` (standalone OCR review UI) is superseded by the staff/doctor scan flow.
- `intake_app.py` (older three-page entry) is superseded.

## (b) Permissions matrix

`K` = kiosk (no login, must send the session's `X-Kiosk-Key`), `S` = staff, `D` = doctor, `-` = refused (401 when not signed in / no key, 403 for wrong role or wrong key). Every mutating request also needs `X-Requested-With: medikiosk` (403 without it).

| Endpoint | Anon | K | S | D |
|---|---|---|---|---|
| GET /api/system/health | yes | yes | yes | yes |
| GET /api/system/config | yes | yes | yes | yes |
| GET /api/system/offline-status | - | - | yes | yes |
| POST /api/auth/login | yes | yes | yes | yes |
| POST /api/auth/logout, GET /api/auth/me | - (me returns 401) | - | yes | yes |
| POST /api/kiosk/sessions | yes | yes | yes | yes |
| GET/POST/PUT /api/kiosk/sessions/{token}/... | - | own token only | - (needs key) | - (needs key) |
| GET /api/intake/body-regions | yes | yes | yes | yes |
| GET /api/doctors | yes | yes | yes | yes |
| GET /api/patients, GET /api/patients/{token} | - | - | yes (staff view) | yes (full view) |
| PUT /api/patients/{token}/vitals | - | - | yes | yes |
| PUT /api/patients/{token}/doctor | - | - | yes | yes |
| GET /api/events | - | - | yes | yes |
| GET /api/staff/help-requests, POST .../{id}/dismiss | - | - | yes | yes |
| POST /api/patients/{token}/scans | - | - | yes | yes |
| GET /api/patients/{token}/scans/{id}/image | - | - | yes | yes |
| GET/PATCH /api/patients/{token}/summary, POST .../summary/paragraph | - | - | - | yes |
| PUT /api/patients/{token}/notes | - | - | - | yes |
| GET /api/patients/{token}/timeline, POST .../timeline/{i}/confirm, POST .../timeline/{i}/discard | - | - | - | yes |
| GET /api/dosing/drugs, POST /api/dosing/history-items, POST /api/patients/{token}/history | - | - | - | yes |
| POST /api/dosing/evaluate, POST /api/dosing/confirm | - | - | - | yes |
| GET /api/audit, /api/audit/verify, /api/audit/export | - | - | - | yes |
| GET /api/demo/fixtures, POST /api/demo/load/{key}, POST /api/demo/kiosk-patient | - | - | - (kiosk-patient: yes) | yes; 404 unless DEMO_MODE=1 |

## (c) API list (final)

All JSON bodies are camelCase pydantic models in `api/schemas.py`. Errors: `{"detail": str}` or, for 422, `{"detail": [{"loc", "msg", "type"}]}` (FastAPI shape) so the forms can map field errors.

System
- `GET /api/system/health` -> `{ok, engineVersion, formularyLoaded}`
- `GET /api/system/config` -> `{demoMode, languages: ["en","hi","mr"], ocrAvailable, formularyLoaded, formularyError, strict}`
- `GET /api/system/offline-status` -> `{level, headline, strict, localModel{host,port,reachable,error}, services[], internet{...}|null, probe{host,port,timeoutS,intervalS}}`

Auth
- `POST /api/auth/login {username, password}` -> `{username, role}` + `mk_session` cookie (httpOnly, SameSite=Strict, Secure when `HTTPS=1`); 401 with the authenticator's message (lockout text included)
- `POST /api/auth/logout` -> 204
- `GET /api/auth/me` -> `{username, role, doctorId}`; 401 `{detail, reason: "idle"|"none"}`

Kiosk (header `X-Kiosk-Key`)
- `POST /api/kiosk/sessions {language}` -> `{token, kioskKey, screen}`
- `GET /api/kiosk/sessions/{token}[?node=<id>]` -> `KioskScreen` `{token, language, stage: consent|question|review|doctor|done|declined, node{id,type,section,text,options[{id,label}],min,max,maxSelections,specials[{id,label}]}, value, progress{done,total}, canGoBack, redFlagMessage}`
- `POST .../answers {nodeId, value}` -> `KioskScreen` (422 with the engine's message on invalid values)
- `POST .../bodymap {nodeId, regions, view, inputMode} | {nodeId, special}` -> `KioskScreen` (server calls `bodymap.make_answer`)
- `POST .../skip {nodeId}`, `POST .../back {nodeId}`, `PUT .../language {language}` -> `KioskScreen`
- `GET .../review` -> `{items:[{nodeId, question, answer}]}`
- `POST .../consent {choice: agree|decline}` -> `KioskScreen` (decline deletes the record)
- `POST .../doctor {doctorId|null}` -> `KioskScreen`
- `POST .../finish` -> `TokenSlip {queueNumber, queueDate, token, doctor{id,name,specialty,room,floor,lineColor,lineName,lineTextColor}|null, room, floor, guidance, estimatedWaitMinutes, patientsAhead, estimateLabel}`; idempotent
- `POST .../help` -> 204; publishes `help.requested`

Reference
- `GET /api/intake/body-regions` -> catalog (viewBox, side/view labels, regions with polygons and labels)
- `GET /api/doctors` -> doctors with room, floor, line colour (text in en/hi/mr)

Staff and doctor
- `GET /api/patients?date=YYYY-MM-DD&status=&q=&mine=` -> `{rows: BoardRow[]}` (queueNumber, token, ageYears, sex, complaint, redFlags[{ruleId, severity, staffMessage, draft, label, triggeredBy[{label, answer}]}], status, assignedDoctor, vitalsPresent, minutesWaiting, pendingScans, updatedAt)
- `GET /api/patients/{token}?lang=` -> `PatientView` (role-filtered: staff gets no doctorNotes, doctorEdits, dosingChecks, visitHistory)
- `PUT /api/patients/{token}/vitals {Vitals fields}` -> `PatientView`; 422 field errors, incl. systolic <= diastolic
- `PUT /api/patients/{token}/doctor {doctorId|null}` -> `PatientView`
- `GET /api/events` -> SSE: `patient.updated`, `redflag.triggered`, `help.requested`, `queue.changed` (each `data: {token, ...}`); heartbeat comment every 15 s
- `GET /api/staff/help-requests`, `POST /api/staff/help-requests/{id}/dismiss`

Doctor only
- `GET /api/patients/{token}/summary?lang=` -> `Summary` (intake/summary.py) + `paragraph` (template)
- `PATCH /api/patients/{token}/summary {lang, values{key: text}}` -> `Summary`
- `POST /api/patients/{token}/summary/paragraph` -> `{source, text, reason}` (local model; template fallback)
- `PUT /api/patients/{token}/notes {notes}` -> `{doctorNotes}`
- `GET /api/patients/{token}/timeline` -> `{confirmed: TimelineEntry[], pending: PendingScan[]}`
- `POST /api/patients/{token}/timeline/{i}/confirm {documentType, documentDate, medications, labResults, diagnosesAsWritten}` -> `{confirmed, pending}` (edited fields computed with `ocr.timeline.edited_fields`, `confirmedBy` = signed-in doctor)
- `POST /api/patients/{token}/timeline/{i}/discard` -> `{confirmed, pending}`

OCR (staff and doctor)
- `POST /api/patients/{token}/scans` multipart `image`, `consent=true` -> `PendingScan {id, uploadedBy, uploadedAt, latencyS, draft}`; 503 `{detail}` when Ollama is down; 422 when unreadable
- `GET /api/patients/{token}/scans/{id}/image` -> JPEG while the OCR temp session lives (`OCR_SESSION_TTL_S`), else 404

Dosing (doctor only; 503 with a clear message when the formulary cannot load)
- `GET /api/dosing/drugs` -> `{drugs:[{id, generic, indications:[{key, labels}], forms}], overrideCategories{}, banner, allowUnverified, demoMode}`
- `POST /api/dosing/history-items {token, drug}` -> `{items, unknown, context{fields[{name,label,value,provenance}], medicines[], unparsed[], ocrUnparsed[]}}`
- `POST /api/patients/{token}/history {answers}` -> `{visitHistory, by, at}`
- `POST /api/dosing/evaluate {token, drug, indication, doctorInputs, confirmed, visitDrugs, selectedRuleId, form, route, showAllRules, overrideReason, overrideCategory}` -> `{resultId, result, card, canConfirm, canConfirmIfAcknowledged}`; 422 when an override is incomplete (message from `override_error`)
- `POST /api/dosing/confirm {token, resultId, acknowledged}` -> `{dosingChecks}`; 409 when `can_confirm` is false or the result id is unknown/expired

Audit (doctor only)
- `GET /api/audit?cursor=&limit=50&patient=&drug=&action=&from=&to=` -> `{rows:[AuditRow], nextCursor, total, totalAll, facets{patients, drugs, actions}}`
- `GET /api/audit/verify` -> `{ok, entries, firstBadIndex}`
- `GET /api/audit/export?format=json|csv&...` -> file download of the filtered rows

Demo (404 unless `DEMO_MODE=1`)
- `GET /api/demo/fixtures` (doctor) -> `[{key, displayName, title, token, drug, indication}]`
- `POST /api/demo/load/{key}` (doctor) -> `{token}`
- `POST /api/demo/kiosk-patient` (staff, doctor) -> `{token}` (the old kiosk chest-pain demo)

## Changes to protected packages (minimal, each with a test)
- `records/schema.py`: optional `queueNumber`, `queueDate`, `finishedAt`, `pendingScans` on `PatientRecord` (defaults keep old records loading).
- `intake/doctors.py`: optional `room`, `floor`, `lineColor`, `lineName` on `Doctor` (the model forbids unknown keys).
- `data/doctors.json`: room, floor and floor-line colour per synthetic doctor (not a forbidden file).
- `scripts/list_unreviewed_translations.py`: also lists the new web UI strings and doctor floor/line names.
- No change to `dosing/`, the formulary, `data/intake_graph.json` or `data/red_flags.json`.

## Known gaps and decisions taken without asking
- Help requests and auth sessions live in memory: a server restart logs staff out and clears open help banners (records and audit are on disk).
- "Patients ahead" counts today's earlier queue numbers for the same doctor (all doctors when "any"): there is no "seen" status in the record, so the estimate does not shrink as patients are seen. It is labelled "estimate".
- OCR images stay only for `OCR_SESSION_TTL_S` (900 s): a doctor confirming a scan later sees the draft without the image.
- The kiosk does not show the offline badge (see open question 3).

- Records layer quirk (pre-existing, not changed): `PatientRecord.socrates` is a union, so a saved radiation answer loads back as `SiteAnswer` with `view`/`inputMode` = null. Harmless for every reader; the parity test compares records after the same JSON round trip.

- "No dose number unless status is ok" is applied more strictly than the Streamlit card: for needs_input (not only blocked/refused) the UI also hides the titration plan, calculation steps, alternative-rule ranges, and the formulary notes and conflicts on alternative rules (they quote doses such as "up to 2550 mg per day"). Engine warnings, interactions and blocks stay visible in every status: they are safety text the doctor must see.

## (d) Open questions (yours to decide; work continues with the default)
1. **Doctor names on the slip.** `data/doctors.json` has realistic synthetic doctor names ("Dr. Asha Kulkarni"). The no-real-names rule is about patients, so I keep them. Default: keep.
2. **Patient wait estimate.** Without a "seen" status the estimate never shrinks. Default: keep the simple estimate; adding a "Mark seen" doctor action would touch the record schema again. Want it?
3. **Offline badge on the kiosk.** Default: not shown to patients (it is staff information and adds noise). Say if judges should see it on the tablet too.
4. **Timeline JSON paste box** on the doctor page is dropped (scan upload replaces it). Default: dropped.

## Phase 7: tests removed with Streamlit

Python tests went 844 (baseline) -> 884 (phases 1-6: +40 in `tests/api/`) -> 828 after removing 55 Streamlit `AppTest` functions (56 items; one is parametrized twice) -> **829** with the doctor-queue ordering test. Three doctor-choice tests in `tests/test_doctors.py` were ported to the API rather than removed. Every removed test drove a deleted Streamlit page; its behaviour is now covered where named.

| Removed | Covered now by |
|---|---|
| `tests/test_intake_ui.py` (all 15): patient flow consent/question/language, decline saves nothing, staff/doctor pages render empty, body-map renders/list selection/max selections/not sure + tell doctor/Hindi labels/back-revisit, doctor page regions and diagram, demo button (4 tests), language label switch | `tests/api/test_api_kiosk.py` (parity, decline, body map built on the server), `web/e2e/kiosk.spec.ts` (Hindi flow, Back, Not sure, decline), `web/src/components/components.test.tsx`, `DemoLoader` + `POST /api/demo/kiosk-patient` |
| `tests/test_flow.py` (all 14): Streamlit step 1/2 sign-in, scan-before-quiz stage, scan attach/confirm, staff vitals then doctor view, systolic > diastolic, staff cannot save notes | `tests/api/test_api_auth_matrix.py` (roles on every route, login, lockout), `tests/api/test_api_errors.py` (scan consent/Ollama down, vitals bounds), `web/e2e/staff.spec.ts` (vitals), doctor timeline confirm endpoint. The scan-before-quiz stage itself was moved to staff/doctor by product decision |
| `tests/test_intake_gate.py` (all 9): `can_edit` doctor only, pages locked when signed out (x2), wrong password lockout, staff sees board, staff view-only summary, doctor edits summary, idle logout, kiosk needs no login, red-flag line readable answers + diagram | `tests/api/test_api_auth_matrix.py` (role matrix incl. summary PATCH doctor-only, kiosk without login, lockout, idle expiry, staff view without doctor fields), `web/e2e/hardening.spec.ts` (summary screen) |
| `tests/test_dosing_ui.py` (all 4): doctor sees banner and runs a check, staff cannot run a check, dosage page runs a check, History check none-apply + override category offered | `web/e2e/doctor.spec.ts` (three scenarios incl. banner, none-apply, override), role matrix (staff 403 on dosing), `tests/api/test_api_dosing.py` |
| `tests/test_auth.py`: `test_app_blocks_until_login`, `test_app_login_flow_and_role_gating`, `test_app_idle_timeout_drops_session` | `tests/api/test_api_auth_matrix.py` (`test_role_matrix`, `test_lockout_after_five_failures`, `test_idle_session_is_logged_out`) |
| `tests/test_doctors.py`: `test_staff_board_shows_chosen_doctor_or_none`, `test_doctor_page_lists_my_patients_first_for_a_linked_login` | board rows carry `assignedDoctor`/`mine` (`api/views.py`), `web/e2e/staff.spec.ts`; my-patients-first ordering in `board_sort_key` |
| `tests/test_demo_features.py`: `test_load_demo_patient_is_hidden_without_demo_mode_and_for_non_doctors`, `test_audit_page_is_doctor_only_and_has_no_edit_controls`, `test_audit_page_shows_chain_broken_after_tampering`, `test_ui_child_fever_reaches_dose_ready_header`, `test_ui_needs_input_checklist_recomputes_inline`, `test_ui_blocked_shows_no_dose_then_override_shows_it_in_red` | `tests/api/test_api_dosing.py` (`test_demo_routes_are_404_without_demo_mode`, `test_audit_pages_newest_first_and_reports_a_broken_chain`), role matrix (audit doctor-only; no edit/delete route exists), `web/e2e/doctor.spec.ts` (all three), `web/src/dosing/ResultCard.test.tsx` |
| `tests/test_region_followups.py`: `test_followup_is_shown_on_the_kiosk_in_hindi` | the follow-up nodes are served by the same kiosk screen endpoint; `tests/api/test_api_kiosk.py` parity runs every scenario through it, `web/e2e/kiosk.spec.ts` (Hindi) |
| `tests/test_bodymap.py`: `test_component_has_no_external_loads` (the deleted Streamlit body-map component HTML) | `tests/test_offline.py` URL scan now covers `web/src` and `api/`; `web/e2e/hardening.spec.ts` offline test |

Kept and re-pointed: `test_card_headers_and_reasons_per_status`, `test_override_requires_category_and_ten_characters`, `test_needs_input_fields_map_to_inputs` now import `api.result_card`.
Also removed with Streamlit: `pandas` (only the old pages used it) and the `streamlit` requirement; `scripts/startup_check.py` now checks fastapi/uvicorn/python-multipart; `scripts/run_demo.py` starts `scripts/run_server.py`.
