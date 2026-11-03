# Prompt for Claude Code: five demo features

Paste everything below the line into the same Claude Code session (it needs the earlier context).

---

Implement five demo features for the OPD project. Keep every earlier hard rule: no LLM in dosing, no invented clinical values, refuse by default, nothing marked clinically verified, synthetic data only, all processing local. Do not change the quiz graph, the red-flag rules or the formulary JSON. Match the repo's language, folder layout, test framework and UI approach. Post a plan of at most 15 lines first (files to touch, any risk you see), then implement, run the full suite, and update docs/DOSING_LOGIC.md and README with the new features and how to run the demo.

## 1. Offline proof indicator
- Add a persistent, small status badge in the app header on every screen, e.g. "Offline mode: no internet used" with the local services listed on hover or expander (the local model server, the local database or file store).
- It must be truthful, not decorative. Implement a lightweight check that runs on page load and every 30 seconds: (a) report the only allowed outbound target (the local model server on localhost) and its reachability; (b) attempt a short-timeout request to one public host and show "Internet: unreachable" or, if it succeeds, "Internet: reachable (not used by this app)" in amber. Make the public host and timeout configurable, default timeout 2 seconds, and never block the UI on it.
- Add a config flag `OFFLINE_STRICT`: when true, any code path that attempts a non-localhost network call raises an error and is logged. Add a test that fails if non-localhost URLs appear in app code (static check) and one test for the strict guard.
- Add a "Demo: turn Wi-Fi off now" checklist note in the demo script (see 2).

## 2. Demo script and fixtures
- Create three synthetic patients as fixtures (quiz answers as JSON, matching the existing answer format and node ids): (a) child with fever, weight-based paracetamol; (b) adult with diabetes and kidney disease, metformin with creatinine entered, plus one run with creatinine missing; (c) adult with penicillin allergy, amoxicillin blocked, then an override with category and reason. Use drugs whose products are on the Indian list. Names must obviously be fictional (e.g. "Demo Patient A").
- Add a "Load demo patient" control, visible only when `DEMO_MODE` is true, that loads a fixture into the normal flow so the demo can start from the doctor screen. It must go through the real code paths, not canned screens.
- Write `docs/DEMO_SCRIPT.md`: a one-page click-through of about 4 minutes with timings, what to say, the exact clicks, expected results (taken from actually running the fixtures, not typed from memory), the Wi-Fi-off step, and a fallback if the local model server is slow (use pre-saved intake answers).
- Add end-to-end tests that run each fixture through the dosing service and assert the status, not hard-coded doses: ok / needs_input / blocked as designed, and that the audit log gets an entry.
- Add a script `scripts/reset_demo_data` (or the repo's equivalent) that clears demo records and the demo audit log, so the demo can be rerun.

## 3. Show refusals clearly
- On the Dosage check result card, give each status a distinct, plain header: "Dose ready for doctor review", "More information needed", "Blocked: safety rule", "Refused: no data for this case". Under each, show the reason in one sentence, the specific input or rule responsible, and the source id and link for blocks.
- `needs_input` must list the exact missing fields as a short checklist the doctor can fill inline, and recompute without a page reload.
- `blocked` must show the override control (reason category: benefit outweighs risk / patient already tolerates it / no alternative available / other, plus free text of at least 10 characters). After override, show the dose with a red "Override recorded" line and write the audit entry.
- Make sure the three fixtures from section 2 each exercise one of these paths. No dose number is ever shown on a blocked or refused card until an override is recorded.

## 4. Audit-log viewer
- Add a read-only "Audit log" page for the doctor role only (match the existing role checks; staff and patient cannot open it).
- Table, newest first: time, doctor, patient (demo id), drug, status, action (evaluated, confirmed, override, history-check answered), with a row expander showing the full stored result: inputs with provenance, calculation steps, warnings, interactions, sources, override category and reason.
- Filters: patient, drug, action, date range. Show a "Chain verified" or "Chain broken" indicator by recomputing the hash chain over the log, plus a test that tampering with one line is detected.
- No edit or delete controls. Export to JSON and CSV buttons for the visible rows, doctor only.

## 5. OCR medicines into interaction checks
- Find where the OCR service parses old prescriptions and lab reports and where the doctor confirms each scan. Reuse that parsed output; do not change the OCR parsing itself.
- Take the medicine names from doctor-confirmed scans only (never from unconfirmed OCR text), normalise them through the existing synonym table, and add them to the current-medicines list used by the interaction check, with provenance `ocr_doctor_confirmed` and a link back to the source scan.
- On the Dosage check result, show interactions that came from scanned prescriptions with a small "from scanned prescription (date)" tag. Medicines the synonym table cannot recognise are listed as "unparsed from prescription: doctor to review", never dropped.
- Merge with the patient's self-reported medicines, de-duplicated, and show both sources. Add tests: a confirmed scan containing warfarin triggers the metronidazole interaction; an unconfirmed scan does not; an unrecognised token is surfaced.

## Deliverables
1. The five features, with tests passing; show the full test output.
2. docs/DEMO_SCRIPT.md, updated README and docs/DOSING_LOGIC.md.
3. A short summary: what you built, what you could not do, assumptions, and open questions.

Do not add features outside this list, change dosing rules or data, call any external service, or mark anything clinically verified.
