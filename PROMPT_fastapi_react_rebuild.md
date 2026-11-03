# Prompt for Claude Code: rebuild the UI as FastAPI + React (patient kiosk, staff, doctor)

Work as a senior full-stack engineer and product manager on this repo (`hack-binary-solo/`). We are replacing the Streamlit UI with a FastAPI backend and a React frontend, keeping the existing tested Python domain code. There are three separate experiences:
- a patient kiosk on a hospital tablet,
- a staff desk,
- a doctor workstation.

**We are also competing for the hackathon's Best UI award.** The interface is not a layer added at the end. Treat design quality as a first-class requirement with its own spec, its own review loop and its own definition of done (section 7). A correct but ordinary-looking app counts as unfinished.

Read this whole prompt before you start. Follow the phases in order. After each phase, run the tests, commit, and give me a short report: what was built, test counts, and any deviations.

---

## 0. Read first (do not code before this)
1. `CONTEXT.md` gives the full project hand-off. `CLAUDE.md` has the hard rules. Also read `docs/DOSING_LOGIC.md`, `docs/DOSING_DATA_ISSUES.md` and `docs/DEMO_SCRIPT.md`.
2. Read every Streamlit page in `intake/ui/` plus `main_app.py`, `app.py` and `intake_app.py`. Then read `intake/session.py`, `intake/engine.py`, `records/`, `dosing/service.py`, `dosing/audit.py`, `dosing/audit_view.py`, `intake/offline.py` and `ocr/auth.py`. This is how you learn the current behaviour, which is the spec.
3. If frontend or design skills are available in your environment (for example a frontend-design skill), read them before designing the UI and follow them. Then write `docs/DESIGN.md` as section 7 describes, before any UI code.
4. Write `docs/REBUILD_PLAN.md` with these parts:
   - **(a) Parity checklist.** List every Streamlit feature and where it will live in the new app.
   - **(b) Permissions matrix.** Use roles × endpoints, with roles kiosk, staff and doctor.
   - **(c) API list.** Final versions of the endpoints in section 4.
   - **(d) Open questions.** Ask me only about things that are genuinely mine to decide.

   Then start Phase 1. Do not wait for an answer unless a hard rule would be broken.

## 1. Product decisions (already made: follow them)
The reference screenshots (a "MediKiosk" prototype: language tiles, ABHA scan, token slip) are for **look and feel only**:
- **Keep from them:** big touch tiles, bilingual labels, a "listen again" button, the calm teal palette, a header with Back and Change language, a help button, and the token slip with a room number.
- **Do NOT copy:**
  - Top tabs on the kiosk linking to EMR, scribe or other screens. A patient tablet must not be able to reach staff or doctor screens.
  - ABHA/Aadhaar scanning or any Ayushman Bharat, NHA, NDHM or government branding. It needs internet, conflicts with our offline design, and would be a fake integration.
  - Claims such as "100% verified", "100% encrypted" or "v2.4 SECURED".
  - Real-looking patient names or ID numbers. Records have only a pseudonym token (`PT-XXXXXX`) and no name field; keep it that way.
  - 8 languages. Only en/hi/mr exist in our data; do not machine-translate the quiz into new languages.
  - AYUSH intake. We have no data for it.
  - An "AI medical scribe".
  - The screenshot's bug of showing "Registration successful!" next to "Token not created yet". Never show success unless the thing exists.
- **Patient flow (kiosk):** Language → Consent → Questions (one per screen, body map included) → Review & edit → Choose doctor (or "Any doctor") → Token slip → auto-reset.
- **Scanning old prescriptions (OCR) happens at the staff desk or the doctor's screen, not on the kiosk.** Staff attaches the scan to the patient's token, and a doctor confirms each scan. This keeps the current rule (doctor confirms) and keeps images off the shared tablet.
- **Voice:** read-aloud only, using the browser's `speechSynthesis`, and only with voices where `voice.localService === true` for the selected language (hi-IN / mr-IN / en-IN). If no local voice exists, hide the button; never pretend. **Never use `webkitSpeechRecognition`/`SpeechRecognition`**: in Chrome it sends audio to Google servers and breaks the offline rule. Voice input is out of scope.
- **Deployment model:** one laptop or PC runs the server. Tablets and staff/doctor screens open it over the hospital LAN with no internet. FastAPI serves the built frontend and the API from one origin.

## 2. Hard rules (unchanged from CLAUDE.md, plus UI rules)
- **Keep these packages as they are:** `dosing/`, `intake/` (non-UI), `records/`, `ocr/`. If you must change one:
  - keep the change minimal and covered by a test,
  - list it in the phase report,
  - and in `dosing/`, change nothing about clinical behaviour. No LLM, network or randomness there, and same input gives byte-identical output.
- Every clinical number comes from the formulary JSON. Never edit the formulary, `data/intake_graph.json` or `data/red_flags.json`. Never mark anything clinically verified. Keep the "Prototype data, not clinically verified" banner on every dosing view, and keep the red "DEMO - UNVERIFIED DATA" bar when the result carries `demo`.
- "Not sure" and "not asked" are unknown, never "no". Quiz answers are immutable; doctor entries stay in their own fields.
- **The server is the single source of truth.** The frontend never computes:
  - quiz flow, red flags or dosing,
  - rounding or blanking of doses.

  It only renders what the API returns. Client-side validation (Zod) is a convenience copy of server rules; the server re-validates everything.
- **Patients never see** dosing output, diagnoses, red-flag rule ids or other patients. The kiosk shows only the red-flag `patientMessage` text, as the current `intake/ui/patient.py` does.
- **Dose display rules:**
  - When status ≠ ok, never render a dose number, even if a field is present.
  - On blocked or refused results, hide dose ranges, regimen, plan, duration and calculation steps, as `result_card.py` does today.
- Overrides need a category plus a written reason of at least 10 characters plus a doctor id. The server enforces this and audit-logs it.
- **Offline:**
  - no CDN, no Google Fonts, no analytics, no maps, no remote images or icons,
  - fonts are self-hosted from npm,
  - the only outbound call the server may make is to `OLLAMA_URL` (localhost),
  - `OFFLINE_STRICT=1` must keep working, and `tests/test_offline.py`'s static URL scan must also cover `web/src` and `api/`.
- Synthetic data only. Any new hi/mr UI text is marked "machine-drafted, needs native review" and must show up in `scripts/list_unreviewed_translations.py`.

## 3. Stack
**Backend: `api/` package at the repo root.**
- **Libraries:** FastAPI, uvicorn, python-multipart and pydantic v2 (already used). Use `httpx` for tests. Add these to `requirements.txt`.
- **Process model:**
  - Run a single uvicorn worker. The record store is JSON files and the audit log is a hash chain.
  - Wrap every operation that writes records or the audit log in one process-wide `threading.Lock`. Endpoints that touch it are sync `def` and run in the threadpool.
  - Reason: `audit.write` reads the last hash and then appends, so concurrent requests would break the chain. Prove the fix with a concurrency test.
- **Layout:**
  - `api/main.py` holds an app factory, `create_app()`.
  - `api/deps.py` holds auth and role dependencies; `api/schemas.py` holds the DTOs.
  - Routers go in `api/routers/` and are named `system`, `auth`, `kiosk`, `patients`, `staff`, `doctor`, `dosing`, `ocr`, `audit` and `demo`.
  - `api/sessions.py` is the intake session registry and `api/events.py` is the SSE broker.
- **Routes and serving:**
  - The API lives under `/api`, with OpenAPI at `/api/openapi.json`.
  - Serve `web/dist` at `/`, with SPA fallback for `/kiosk/*`, `/staff/*` and `/doctor/*`.
  - Bind to 0.0.0.0 so LAN tablets can connect.
- **Auth:**
  - Reuse `ocr/auth.py` (`users.json`, password hashing, lockout after 5 failures, idle timeout `OCR_AUTH_IDLE_S`).
  - Keep the server-side session in memory, with an httpOnly cookie that is `SameSite=Strict` and `Secure` only when HTTPS is on.
  - Every mutating request must carry a custom header (`X-Requested-With: medikiosk`) as a CSRF guard.
  - Roles: `staff` and `doctor`, with the same rights as today (`gate.can_edit` = doctor only).

**Frontend: `web/`.**
- **Core:** Vite, React 19, TypeScript in strict mode (no `any`), Tailwind CSS (follow the installed version's docs; v4 is CSS-first) and React Router.
- **Data and types:**
  - TanStack Query for server state; Zod for form schemas.
  - Generate types from OpenAPI with `openapi-typescript`, via `npm run gen:api`, and commit the generated file.
  - lucide-react for icons; `@fontsource/noto-sans` and `@fontsource/noto-sans-devanagari` for fonts.
- **Testing:** Vitest with Testing Library, and Playwright with `@axe-core/playwright`.
- **Structure:**
  - One SPA with three route trees, each with its own layout and code-split chunk: `/kiosk`, `/staff` and `/doctor`.
  - `/` is a small chooser for the demo laptop. A tablet is simply bookmarked to `/kiosk`.
- **Dev and run:**
  - In development, the Vite dev server proxies `/api` to `:8000`.
  - Add one run command (`scripts/run_server.py` or a Makefile target) that builds `web/` if needed and starts uvicorn.
  - Document `DEMO_MODE=1` and `OFFLINE_STRICT=1` usage with it.

Use these patterns from my earlier prompt examples where they fit. Skip the rest:
- **Dashboard shell** (collapsible sidebar, sticky header, drawer below md, focus trap, Esc, persisted state): use it for the staff and doctor layouts.
- **React 19 form Actions** (`useActionState`, `useFormStatus`, Zod, `aria-live` errors, focus on the first error): use them for login, vitals, override, dosing inputs and history check. This is a SPA, so drop the "works with JS disabled" requirement.
- **Data table** (generic `Table<T>`, sort with `aria-sort`, debounced search, select-all scoped to the filtered view, sticky first column): use it for the staff board and the audit log.
- **Infinite scroll with cursor pagination and `useInfiniteQuery`** (no double fetch, retry without losing rows): use it for the audit log.
- **Theme system** (light/dark/system, no flash, semantic CSS-variable tokens): use it for staff and doctor. The kiosk stays light, with an "A+ larger text" toggle.
- **Button library** (primary, secondary, ghost, danger with confirm, loading with no width shift, success, icon-only with a required label at the type level, toggle with `aria-pressed`): use it everywhere.
- **Carousel:** do not build one. Nothing in this product needs it.

## 4. API (refine it in REBUILD_PLAN.md, but keep the shape)
Every response uses pydantic models. Engine results are returned exactly as `dosing.service` produces them, wrapped as `{result, card}`. Do not reshape or recompute engine fields. `card` comes from the pure `result_card.card_model()`, moved to `api/` and keeping its tests.

**System**
- `GET /api/system/health`
- `GET /api/system/offline-status`, which wraps `intake.offline.status()`.
- `GET /api/system/config`, returning `demoMode`, `languages`, `ocrAvailable` and `formularyLoaded`.
- If the formulary is missing, intake still works and the dosing endpoints return 503 with a clear message.

**Auth**
- `POST /api/auth/login`, `POST /api/auth/logout` and `GET /api/auth/me`.

**Kiosk (no login)**
- `POST /api/kiosk/sessions {language}` creates a session and returns `{token, kioskKey}`. `kioskKey` is a random secret kept only in the tablet's `sessionStorage`. Every later kiosk call must send `kioskKey`. No kiosk endpoint can list or read other tokens.
- `GET /api/kiosk/sessions/{token}` returns the current screen:
  - node id, type, section,
  - text and options in the chosen language with English fallback,
  - `min`/`max`, `maxSelections`, specials,
  - `progress` from `session.progress()`, `canGoBack`,
  - and the red-flag `patientMessage` if one fired.
- Questions:
  - `POST .../answers {nodeId, value}` validates with `intake.engine.validate_answer` and returns the next screen.
  - `POST .../skip {nodeId}`
  - `POST .../back`
  - `PUT .../language`
- Body-map answers are built on the server with `intake.bodymap.make_answer`, from `{regions, view, inputMode}` or a special option.
- `GET .../review` lists the answers with labels. Editing a past answer re-runs `recompute_path`.
- `POST .../consent {agree|decline}`. Decline deletes the record, as today.
- `POST .../doctor {doctorId|null}`
- `POST .../finish` creates the token slip; see section 5.
- `POST .../help` raises a "patient needs help" alert on the staff board.
- **Session registry:** `IntakeSession` lives in memory, keyed by token. After a server restart, rebuild it from the saved record's answers. Add a test proving that the rebuilt session produces the same record.

**Reference data**
- `GET /api/intake/body-regions` serves the polygons and labels from `data/body_regions.json`.
- `GET /api/doctors`

**Staff and doctor**
- `GET /api/patients?date=&status=&q=` serves today's board: queue number, token, age/sex, complaint, red flags (urgent first, with `draft` label and triggering answers), status, assigned doctor, vitals present, minutes waiting.
- `GET /api/patients/{token}` returns a role-filtered view. Staff never get dosing checks or doctor notes unless the current Streamlit staff page already shows them; check it.
- `PUT /api/patients/{token}/vitals` uses the `records.schema.Vitals` bounds and returns 422 field errors.
- `PUT /api/patients/{token}/doctor` reassigns the doctor (staff and doctor).
- `GET /api/events` is Server-Sent Events, with event types `patient.updated`, `redflag.triggered`, `help.requested` and `queue.changed`. Fall back to polling every 10 s if the stream drops.

**Doctor only**
- `GET/PATCH /api/patients/{token}/summary` serves the deterministic summary (`intake/summary.py`) with edit tracking.
- `PUT .../notes`
- `GET .../timeline`
- `POST .../timeline/{i}/confirm` takes the edited fields and records `confirmedBy`.

**OCR (staff and doctor)**
- `POST /api/patients/{token}/scans` is a multipart image upload that runs `ocr.service.extract` and returns the draft. Upload with `<input type="file" accept="image/*" capture="environment">`, which works over plain HTTP on the LAN; `getUserMedia` needs HTTPS.
- If Ollama is down, return a clear 503. The rest of the app keeps working.

**Dosing (doctor only)**
- `GET /api/dosing/drugs` returns ids, generic names and indications from the formulary.
- `POST /api/dosing/history-items {token, drug}` returns the unknown History-check items.
- `POST /api/patients/{token}/history {answers}` calls `service.save_history`.
- `POST /api/dosing/evaluate` mirrors `service.evaluate_for_record`'s arguments exactly.
- `POST /api/dosing/confirm {token, resultId|request, acknowledged}`: the server re-evaluates (or uses a server-side cached result keyed by id), checks `can_confirm`, and calls `service.confirm`. Never trust a client-sent result.

**Audit (doctor only)**
- `GET /api/audit?cursor=&limit=50&patient=&drug=&action=&from=&to=` returns newest first, using `audit_view.rows`/`filter_rows`.
- `GET /api/audit/verify`
- `GET /api/audit/export?format=json|csv&<same filters>`
- Cache the parsed log by file size and mtime; it is already about 10 MB.

**Demo (only when `DEMO_MODE=1` and role is doctor)**
- `GET /api/demo/fixtures`
- `POST /api/demo/load/{key}`, using `dosing/demo.py`.

## 5. Token slip and queue (new; keep it small)
- Add optional fields to `PatientRecord`: `queueNumber`, `queueDate` and `finishedAt`. Defaults must keep old records loading. Add `room` and `floor` to `data/doctors.json`; it is synthetic data.
- `finish`:
  - assigns the next number in one daily OPD sequence, under the lock,
  - is idempotent: calling it twice returns the same number,
  - and returns `{queueNumber, token, doctor (or null), room/floor (or "Reception will guide you"), estimatedWaitMinutes, patientsAhead}`.
- The wait estimate is `patientsAhead × OPD_MINUTES_PER_PATIENT` (env var, default 10), always labelled "estimate".
- The slip has a print stylesheet and calls `window.print()`. It shows only the queue number, token, doctor and room. No name, no answers, no red flags.
- The success header appears only after `finish` returns 200. On failure, show "Something went wrong, please show this screen to staff" with a retry button.

## 6. UX per surface
**Kiosk (tablet, portrait and landscape, about 800×1280).**
- **Patients:** may be elderly, semi-literate or anxious, and are using a shared device.
- **Sizing:** tap targets at least 64 px, body text at least 20 px, question text at least 30 px. One question per screen; options fit without scrolling where possible.
- **Header on every screen:** Back, the question text, a "Listen again" button (only when a local voice exists), Change language and Help (calls staff).
- **Answer controls:** "Not sure" and "Skip" sit as clearly separate secondary buttons on every non-consent question. "Not sure" is an answer; skip is not.
- **Input types by node type:**
  - `single_choice` and `yes_no_unsure`: large tiles.
  - `multi_choice`: tiles plus "Continue", with `none` exclusive.
  - `number`: a big numeric keypad with the min/max shown.
  - `scale_0_10`: 11 large buttons with end labels.
  - `free_text`: a big textarea, with Skip offered.
  - `body_map`: an SVG drawn from `body_regions.json` with front/back toggle. Tapping highlights a region. Always offer a "Choose from a list" alternative, "I'm not sure" and "I'd prefer to tell the doctor". Label the sides "Patient's right" and "Patient's left". Hit-testing may be done in the browser for highlighting, but the server builds and validates the answer.
- **Progress:** a calm progress bar, not "question 7 of 73"; the path is adaptive.
- **Review screen:** list every answer with an edit button.
- **Idle reset:**
  - After 90 s idle, show "Are you still there?" with a 30 s countdown.
  - Then clear `sessionStorage` and in-memory state and return to the language screen.
  - The record stays `in_progress` on the server for staff to see.
  - After the token slip, auto-reset after 60 s, with a "Done" button.
- **No staff/doctor reachability:** no browser chrome is needed, no links to `/staff` or `/doctor`, and no dev tools text. Document how to pin the tablet (Android screen pinning or kiosk browser).
- **Red-flag message:** show the `patientMessage` as a calm card with an icon and text (not colour alone), and let the patient continue, as today.

**Staff desk (laptop or desktop).**
- **Layout:** sidebar with Board, Patient, Scans and Help requests. The header holds the offline badge, user menu and theme toggle.
- **Board:**
  - live via SSE; urgent red flags pinned on top with icon and text plus a subtle sound the user can mute,
  - help requests appear as a dismissible banner,
  - a data table with search, sort and filters.
- **Patient panel:**
  - the summary of answers in English, plus a language toggle for hi/mr display,
  - red flags with rule id, "Draft rule, source check pending" and the triggering answers,
  - a vitals form, doctor reassignment, and scan upload whose OCR draft is sent to the doctor for confirmation.
- **No dosing anywhere.**

**Doctor workstation (laptop).**
- **Layout:** sidebar with My queue, Patient, Audit log and (demo) Load demo patient. The header holds the offline badge and theme toggle.
- **Patient workspace sections:**
  - Summary: editable, edit-tracked, answer-language toggle, small body diagrams with site in red and radiation in orange, red flags.
  - Vitals.
  - Timeline: confirm or edit pending scans.
  - Notes.
  - Dosage check.
  - Dosing record: confirmed checks and overrides.
- **Dosage check (the core of the demo). Mirror `intake/ui/dosing_panel.py` and `result_card.py` exactly:**
  - **Inputs:** searchable drug combobox, indication select, then optional form, route, other drugs this visit and "show every rule".
  - **History check:** shows only unknown items, plus "None of these apply" and Save.
  - **Before running:** a weight-confirmation checkbox, then **Run dosage check**.
  - **Result card headers:** "Dose ready for doctor review", "More information needed" (with an inline checklist per missing field and **Update and recompute**), "Blocked: safety rule" (with the source id, name and link text, and the override form), "Refused: no data for this case".
  - **Calculation steps:** in a disclosure.
  - **After an override:** a red "Override recorded" line.
  - **Confirm button:** disabled until the server says `canConfirm`, which requires the "I have checked these" tick when `acknowledge_items` exist.
  - **Banners:** the prototype banner is always visible; the DEMO bar shows when `demo`.
- **Audit log:**
  - infinite table, newest first, with filters and a row expander (inputs, provenance, steps, warnings, interactions, blocks, sources, override category and reason),
  - "Chain verified" or "Chain broken" in text plus icon,
  - export of the filtered rows,
  - and never any edit or delete control.

The visual design, tokens and review process are in section 7.

## 7. UI quality bar: designing for the Best UI award
Judges spend about a minute with each team, so the app must look deliberate and feel fast in that minute. It must also be visibly built for its real users: a semi-literate patient on a shared tablet, a busy desk clerk, and a doctor between patients. Generic dashboard looks lose. So does decoration that gets in the way.

### 7.1 Design concept (refine it in DESIGN.md; do not replace it with a generic look)
Ground the look in the real world of an Indian district-hospital OPD:
- **The paper OPD case slip (parchi).** Patients already know it, so the token slip should feel like a clean, modern parchi rather than a web card.
- **The coloured lines painted on hospital floors that lead to each department.** Give every doctor/room a line colour (`lineColor` in `data/doctors.json`, synthetic). The token slip and the "you are here → room" strip then say "Follow the green line to Room 12", with that colour shown as a thick stripe. This is the kiosk's signature moment; spend the boldness there.
- **Big, clear, bilingual type.** It should read like good public signage.

The doctor and staff screens are calmer and denser, like a clinical workstation. The patient's own words, the safety state and the dose are the loudest things on screen; everything else stays quiet.

**Avoid the tells of generated UI:**
- every block as an identical rounded card with the same grey shadow,
- gradient washes,
- tracked-out ALL-CAPS labels above every heading,
- "A · B · C" meta strings and arrows appended to button text,
- cream backgrounds with terracotta accents,
- near-black with neon accents,
- numbered markers on things that are not sequences.

Calculation steps and the quiz progress *are* sequences, so numbering them is fine.

### 7.2 Starting tokens (verify contrast; adjust in DESIGN.md only with a reason)
- **Palette:**
  - Ink `#14302D`, used for text instead of black.
  - Hospital teal `#0B5A55`, for primary actions and the brand.
  - Paper `#FAFBF8`, the background (cool, not cream).
  - Teal tint `#E3F0EE`, for selected and quiet surfaces.
  - Marigold `#F2B33D`, for attention fills, always with ink text and never as text on paper.
  - Signal red `#B42318`, for urgent and blocked only.
  - Leaf green `#1C7A4C`, for ok and confirmed.
  - Muted `#4F6461`, for secondary text.
  - Dark theme (staff/doctor): background `#0F1E1C`, text `#E6EFED`, teal `#5CC4B8`.

  I checked these pairs: all are at least 5:1 contrast, so they pass AA. Re-check any colour you add, including the floor-line colours used behind text.
- **Type:**
  - Noto Sans with Noto Sans Devanagari, self-hosted. They are designed to sit together, so use one family with deliberate weights; don't add a second decorative face.
  - Build a clear modular scale. On the kiosk, the question text is the hero: big, heavy, and in the patient's script.
  - Use tabular numerals for doses, tokens, times and vitals.
- **Devanagari rules:**
  - Line-height at least 1.5 for body text and at least 1.3 for headings, so matras and conjuncts are never clipped.
  - No letter-spacing and no synthetic italics on Devanagari.
  - Test the longest Marathi and Hindi strings for wrapping and truncation.
- **Spacing:** a 4/8 px grid.
- **Radii follow hierarchy:** tiles, panels and pills get different radii, not one radius everywhere.
- **Elevation:** two or three levels at most. Use borders and surface colour before shadows.
- **Motion tokens:** 120 ms for feedback, 200–280 ms for screen changes, and one easing curve. Everything collapses to instant under `prefers-reduced-motion`.

### 7.3 Signature moments (put the polish here first)
1. **Kiosk question screen.**
   - Huge question text, with tiles that respond within 100 ms of a tap: a pressed state, then a selected state with a check icon and text.
   - Screen changes follow direction: forward slides one way, Back slides the other. This is the only non-trivial motion on the kiosk.
   - Optional `navigator.vibrate(10)` on tap where supported, off when reduced motion is on.
2. **Body map.**
   - A clean, original SVG figure (no third-party art) with front/back flip.
   - Selected regions fill with teal and their names appear as removable chips in the patient's language.
   - The "Choose from a list" alternative always sits one tap away.
3. **Token slip.**
   - The parchi layout: a large queue number, then doctor and room, then the floor-line colour stripe with the "follow the line" text.
   - Print-ready.
   - A short success moment, shown only after the server confirms: a stamp-like check animation that is instant under reduced motion.
4. **Dose result (doctor).** For `ok` results only, render a **dose ruler** from engine fields:
   - the rule's `dose_range_mg` band,
   - the delivered `dose_mg` marker,
   - and a second bar for `daily_total_mg` against `daily_max_mg`, with `binding_cap` labelled.

   It is drawn purely from returned numbers; the UI never calculates or rounds. For blocked, refused and needs_input, show no ruler and no numbers. Show the calculation steps as a numbered, readable sequence in a disclosure.
5. **Audit chain.**
   - Show the log as a visual chain: each entry linked to the previous one by a short hash prefix.
   - "Chain verified" appears as a seal with icon and text; "Chain broken" is red, with the first bad entry highlighted.
6. **Staff board.**
   - An urgent red flag enters with one attention animation, then stays still.
   - It shows the rule name, "Draft rule, source check pending" and the triggering answers. It never relies on colour alone.
7. **Offline badge.** A polished status pill: "Offline: no internet used" with a small live indicator, opening to network details. Judges should *see* the offline promise.

### 7.4 Interaction and content rules
- **Primary actions:** one per screen, visually obvious.
- **Labels:** buttons say exactly what happens ("Save vitals", "Run dosage check", "Record override"). The same action keeps the same name in its toast or confirmation.
- **Copy style:** sentence case and plain verbs, with no filler or marketing copy anywhere.
- **Errors:** say what happened and how to fix it, and never apologise. Empty states tell people what to do next ("No patients yet today. New patients appear here as soon as they start on the kiosk.").
- **Loading:** skeletons match final dimensions, with zero layout shift. Optimistic UI only for non-clinical things (theme, filters), never for answers, doses or confirmations.
- **Kiosk modes:** "A+ larger text" and "high contrast" toggles that persist only for the current patient session.
- **Doctor/staff:** light, dark and system themes, with dark designed deliberately rather than inverted. Keyboard shortcuts for frequent actions (next patient, run check, focus search), listed under a "?" overlay.
- **Responsive:** kiosk is tablet-first in both orientations. In landscape the question sits left and answers right; in portrait they stack. Staff and doctor screens work from 1280 px wide down to a 360 px phone without horizontal scroll.

### 7.5 Design process (required)
1. **Before UI code, write `docs/DESIGN.md`.** It contains:
   - the concept in three sentences,
   - final tokens (palette with hex values and contrast table, type scale, spacing, radii, elevation, motion),
   - ASCII wireframes of the kiosk question, body map, review, token slip, staff board, doctor workspace, dose result and audit chain,
   - and a short self-review listing anything that looked like a generic default and what you changed.
2. **Build `/gallery`**, a dev and `DEMO_MODE` route showing every component in every state (all eight button variants, tiles, inputs with errors, the four result-card statuses, the dose ruler, red-flag rows, empty, loading and error states). Show each in en/hi/mr and in light/dark. Use it for review and in the pitch.
3. **Screenshot review loop.**
   - `web/e2e/screens.spec.ts` captures every key screen at 800×1280, 1280×800, 1440×900 and 360×740, in en and hi, and light/dark where relevant, into `docs/screens/`.
   - After each UI phase, look at the screenshots yourself and fix problems before moving on. Check against this list:
     - hierarchy readable in three seconds,
     - one primary action,
     - grid alignment,
     - no clipped Devanagari, no truncated Marathi,
     - contrast,
     - touch targets at least 64 px on the kiosk,
     - no layout shift,
     - nothing that looks like a template.

     Then remove one unnecessary decoration from each screen.
   - Report what you changed after each review.
4. **Performance budget:** the kiosk route chunk is at most 150 KB of gzipped JavaScript, first screen appears in under 1 s on the LAN, and interactions respond in under 100 ms. Check them with a production build.

## 8. Phases (commit after each; tests green before moving on)
1. **API foundation and design base.**
   - Set up the `web/` scaffold with the tokens from `docs/DESIGN.md`, self-hosted fonts, the button library, the layouts and the `/gallery` route.
   - Run the first screenshot review of `/gallery` before any feature screen is built.
   - Build the app factory, system and auth endpoints, role dependencies, lock, SSE broker and OpenAPI.
   - Add `tests/api/`: an auth/role matrix test hitting every route as anonymous, kiosk, staff and doctor (401/403), plus the lock concurrency test.
   - Run 20 parallel evaluate+confirm calls, then assert `audit.verify()` is true.
2. **Kiosk.**
   - Build the kiosk API and the full kiosk UI.
   - **Parity test:** replaying the three demo fixtures and the synthetic bank through the API gives the same `PatientRecord` as `IntakeSession` directly, apart from timestamps.
   - Add a Playwright e2e of the full Hindi flow from language to token slip.
   - Run the screenshot review (7.5) on every kiosk screen in en, hi and mr, in both orientations.
3. **Staff.**
   - Build the board with live SSE, the patient panel, vitals, scans and help requests.
   - Add an e2e test: a kiosk red-flag path appears on the staff board without a reload.
4. **Doctor.**
   - Build the summary, timeline confirmation, notes, Dosage check, audit log and demo loader.
   - **Determinism test:** API `/dosing/evaluate` returns a result byte-identical to `service.evaluate_for_record` for the same inputs.
   - **e2e:** the three `docs/DEMO_SCRIPT.md` scenarios reach the expected statuses and numbers from the fixtures. Take the numbers from `scripts/dosing_demo.py` output, not from memory.
   - Add a unit test that no dose number renders when status ≠ ok, and that the dose ruler renders only for `ok`.
   - Run the screenshot review on the staff and doctor screens in light and dark.
5. **Hardening.**
   - Run axe on the kiosk screens, board, dosage check and audit log, with zero serious or critical violations.
   - **Offline e2e:** Playwright aborts every non-localhost request; assert none were attempted and that the fonts load.
   - Test at viewports 800×1280, 1280×800, 1440×900 and 360×740.
   - Cover these error states: Ollama down, formulary missing, server restart mid-quiz (session rebuilt), double-tap on finish (same token), two tablets at once, and a broken audit chain (shown, never auto-fixed).
6. **Retire Streamlit.** Do this only after phases 1–5 pass.
   - Move the pure helpers (`card_model`, `override_error`, `field_kind`, `audit_view` usage) and their tests into `api/`.
   - Delete the Streamlit pages, `main_app.py`, `intake_app.py`, `app.py` and the `streamlit` requirement.
   - Update `README.md`, `CLAUDE.md`, `CONTEXT.md` and `docs/DEMO_SCRIPT.md` (new click-through with the new URLs).
   - Report the final test count against the starting 838. Every removed test must be named, with the reason.

**If time is short** (a hackathon demo): build a demo slice first and keep the Streamlit app runnable until Phase 6. The slice is Phase 1 (minimal), then the doctor Dosage check, audit log and demo loader, then the kiosk happy path, then the staff board.

## 8. Done when
- A patient can finish the quiz in hi, mr or en on a tablet with touch only, get a correct token slip, and the tablet resets itself.
- Staff see new patients, red flags and help requests live, without a reload.
- A doctor can run the three demo scenarios end to end with the same statuses and numbers as the Streamlit version, and the audit chain is still verified.
- Every endpoint enforces its role, the kiosk can never read another token, and the server makes zero non-localhost calls (`OFFLINE_STRICT=1` passes).
- All Python tests pass, plus the new API, Vitest and Playwright suites.
- `docs/REBUILD_PLAN.md` parity checklist is fully ticked, and any remaining gap is listed honestly.

Ask me before you:
- add a dependency that needs internet at runtime,
- change clinical behaviour,
- edit a forbidden data file,
- or delete anything outside Phase 6.
