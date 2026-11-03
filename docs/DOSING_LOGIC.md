# Dosage-check logic

Decision support for registered doctors. The doctor decides. **Prototype data, not clinically verified**: every formulary drug is `verified: false`.
Code: `dosing/` (engine), `intake/ui/dosing_panel.py` (doctor screen). No LLM, no network, no randomness; same input gives byte-identical output.

## Status values
`blocked` (unoverridden hard stop) > `refused` (no rule / unknown drug / UNVERIFIED rule with `DOSING_ALLOW_UNVERIFIED` off / incomplete rule) > `needs_input` (a missing fact, listed with why) > `ok`.
Number fields are blanked unless the status is `ok` (or `needs_input` for product choice, where the closest options are listed).
A result is `final` only when status is ok, a number was computed and weight (and creatinine, when a renal measure was used) is doctor-entered or doctor-confirmed.

## Config
`DOSING_ALLOW_UNVERIFIED` (default false), `DOSING_ML_STEP` (0.5), `DOSING_ABW_FACTOR` (default: formulary `factor_default`), `DOSING_FORMULARY_PATH` (default: the in-repo copy `data/dosesafe_formulary_v2.json`, a verbatim copy of `Final_Drugs_data/dosesafe_formulary_v2.json`; update it by copying the original again). Override reason minimum length: 10 characters (`Config.override_min_chars`).

## Quiz to context (`dosing/mapper.py`)
Unknown = not asked, skipped or "not sure"; it is never "no". Whether a node was asked is read from the quiz graph (`recompute_path`), not copied thresholds.
| Context | Quiz node | Rule |
|---|---|---|
| age_months | `age_years`, `age_months` | years 0: months, no window. Else years x 12 with an 11-month window; a rule boundary inside the window gives `needs_input` for exact age (`age_exact_days`). |
| sex / sex_for_formula | `sex` | `other` or skipped: doctor chooses for formulas. |
| pregnant | `pregnancy` | yes / no / unsure = `possible` / skipped = unknown. Not asked: derived `no` only if the quiz passed that point (male, or outside the graph's age band). |
| weight_kg | `weight_kg` | patient_reported; draft plausibility warning only (`data/plausibility.json`, unsourced). |
| allergy_* | `allergies` | `none` exclusive: all classes known `no`. Skipped/unsure: unknown. |
| allergy_other, meds | `allergy_other`, `meds_any`, `meds_list` | Normalised via `data/med_synonyms.json`; unrecognised tokens shown as "unparsed: doctor to review". |
| kidney/liver/diabetes/hypertension/asthma | same ids | yes / no / unknown. |
| ulcer, alcohol, stones | `hx_abdomen` | unknown off the abdominal branch. |
| gi_bleed | `danger_signs` (vomit_blood, black_stool) | |
| heart_disease, smoking | `hx_chest`, `hx_cough` | unknown off those branches. |
| red flags, complaint | record red flags, `chief_complaint` | read-only context. |
Doctor-only fields (never defaulted): drug, indication, height, creatinine, breastfeeding, Child-Pugh, QT history, G6PD, dialysis, pregnancy weeks/trimester, form, doses per day, mg/kg/day.
Provenance: `patient_reported`, `doctor_entered`, `doctor_confirmed`, `derived`, `unknown`.

## Rule selection conventions
* Indication key = label text before the first `,` or `(` (lower case). `any` / `all indications` rules match every indication. "Show every rule" lists all rules that fit the patient.
* Age: min inclusive; max inclusive through the completed unit (`max_age_years: 17` = to 17 y 11 m). Weight: min inclusive, max exclusive.
* Empty population `{}`: paediatric (age < 18) when the dose is weight-based; otherwise applies with a "population unspecified" warning.
* Adult rule = `min_age_years >= 18`. Adult rules supersede open-ended weight-based rules for adults. Drug `adult_switch` (amoxicillin-clavulanate, 40 kg): at or above that weight the adult rule applies regardless of age.
* Rules with identical dose content from different sources are merged; the best-status one is shown and the others listed as corroborating.
* More than one live rule: all are returned, the first VERIFIED (else SECONDARY) is `suggested_rule_id`, and the doctor must choose (`selected_rule_id`).
* Rule `options`: dict options become separate pseudo-rules (`drug#3.0`); free-text options are shown as text and never computed.
* A rule with no `route` is oral.

## Blocks versus warnings
Blocks (overridable only with a typed reason, logged): allergy class, free-text allergy hitting the drug, contraindication/block_rule predicate true, pregnancy contraindication (yes or possible), age/weight outside every rule, renal band "Contraindicated / Do not use / Do not start", blocking interaction (`block`, `contraindicated`), child off-label (`override_rules`).
Warnings: possible pregnancy text, lactation (doctor-entered), hepatic and renal notes, relevant label warnings (`safety_map.json` triggers), non-blocking interactions, free-text items the engine cannot check ("Not machine-checked, doctor to confirm"), unconfirmed weight.
Needs input: any fact a contraindication depends on that is unknown (ulcer on non-abdominal paths, pregnancy skipped, allergies skipped, current medicines unknown, QT history for qt_risk drugs, creatinine when kidney disease is yes/unsure/unknown and the drug has numeric renal bands).

## Calculation
Formulas are evaluated from the formulary's `formulas` strings by a whitelisted AST evaluator. Renal measure named by a rule is the one used (`CrCl` and `GFR` use Cockcroft-Gault per the formulary `unit_rule`; `eGFR` uses CKD-EPI 2021 for adults or bedside Schwartz for 1-16 y); the steps say which. Renal action text is applied to the dose only for adult fixed rules and only when it parses as "N mg every H h / once daily"; otherwise a warning asks the doctor to adjust.
Caps: per dose, per day, per kg per day, per course, max doses per day, `range_mg`, hepatic max, and formulary `defaults.<drug>_child` for children when the rule is silent. The binding cap is reported; products are never rounded above a bound cap. Liquids: mL rounded to `DOSING_ML_STEP`, delivered mg reported, half a step of slack against the range. Tablets: whole only (no scored flag exists in the data). Solid forms are preferred when in range.
Amoxicillin-clavulanate is computed on the amoxicillin component and matched to products by ratio key (`200/28.5`).

## Result fields
`status, drug, indication, selected_rule_id, suggested_rule_id, alternatives[], dose_mg, dose_range_mg, product, product_options[], volume_ml, units, interval_h, doses_per_day, daily_total_mg, daily_max_mg, binding_cap, duration, plan, text_regimen, computed, calculation_steps[], warnings[], label_warnings[], blocks[], needs_input[], refused_reasons[], interactions[], overrides[], provenance, sources[], data_status, final, pending_confirmations[], indications[], engine_version, formulary_version, banner`.

## Audit
`dosing/audit.py` appends hash-chained JSONL to `<INTAKE_DATA_DIR>/audit/dosing_audit.jsonl`: every evaluation, each override, each confirmation, with result, inputs, provenance, doctor id and reason. Confirmed checks are also stored in `PatientRecord.dosingChecks`; quiz answers are never modified.

## Adding a drug
1. Add it to the formulary JSON (the engine is read-only on that file). Run `pytest tests/test_dosing_data.py`: it fails on any unsupported `dose_type`, field, form or strength shape.
2. Add a `med_synonyms.json` entry with `drug_id` and labels that include the canonical `duplicate_class` (and `qt-prolonging` if `qt_risk`).
3. Add `safety_map.json` `ci_map` entries for its contraindication / block_rules texts; unmapped text still appears as "doctor to confirm".
4. Add tests for its specific rules.

## Update 2

### Age boundaries
Completed-age convention and strict minimum-age checks are unchanged. When every live rule matches because the patient's completed age equals a stated bound (for example 6 y against cetirizine 2-6 and 6-12), the engine returns all of them in `alternatives`, lists them in `boundary_overlap`, defaults `selected_rule_id` to the lower-dose rule (lowest daily total, then the earlier rule) and warns. The doctor can pass another `selected_rule_id`. The data overlaps are listed in DOSING_DATA_ISSUES.md.

### Heart disease
The broad quiz answer (`hx_chest.heart`) no longer blocks or warns. Contraindications that mention heart failure or ischaemic heart disease become a `question` item whose field is `q_<hash of the text>`, quoted exactly from the formulary. Not answered or "unsure": `needs_input`. "yes": block with that text. "no": nothing.

### History check
`dosing/history.py` lists the yes / no / unsure facts the selected drug's contraindications, warnings, renal, hepatic, pregnancy and lactation text depend on (allergy classes, ulcer, GI bleed, alcohol, asthma, diabetes, hypertension, kidney, liver, pregnancy, breastfeeding, QT, and every contraindication question). The panel shows only the unknown ones at the top, with a "None of these apply" button that sets them all to no. Saved answers go to `PatientRecord.visitHistory` (provenance `doctor_confirmed`), apply to every drug checked in the visit, and are audit-logged (event `history`). "Unsure" is stored as unsure (pregnancy: `possible`) and always counts as unknown.

### Overrides
A block can be overridden only with a category (`benefit_outweighs_risk`, `patient_tolerates`, `no_alternative`, `other`) and a written reason of at least 10 characters, plus a doctor id. Both are in the audit entry (`override_category`, `override_reason`), in the result's `overrides[]`, in `PatientRecord.dosingChecks`, and on the doctor summary ("Dosing record").

### Weight plausibility
Cited WHO CGS / WHO 2007 / IAP 2015 tables are used (about -3 SD to +3 SD, sex-specific, nearest age at or below) when filled in `growth_reference.json`. The file currently has structure only ("needs data"), so the labelled DRAFT table is used. The flag never corrects the weight.

### Demo mode
`DOSING_DEMO_MODE=1` sets `DOSING_ALLOW_UNVERIFIED` on and adds `demo` / `demo_banner` ("DEMO - UNVERIFIED DATA") to every result; the panel shows it as a red bar. `dosing/demo.py` has three synthetic patients; `.venv/bin/python scripts/dosing_demo.py` prints them as text. Tests: `tests/test_dosing_scenarios.py`.

## Update 3: demo features

### Offline proof (`intake/offline.py`, `intake/ui/offline_badge.py`)
A badge above every page (all three entry apps) states the only allowed outbound target (`OLLAMA_URL`, localhost) and whether it answers, lists the local services (model server, data folder) under *Network details*, and shows the result of one short TCP probe to a public host (`OFFLINE_PROBE_HOST`, default `1.1.1.1:443`, `OFFLINE_PROBE_TIMEOUT_S` default 2): "Internet: unreachable", or amber "Internet: reachable (not used by this app)". The probe runs in a background thread, is cached and refreshed every `OFFLINE_CHECK_INTERVAL_S` (30); the UI never waits on it. `OFFLINE_STRICT=1` patches socket connects so any non-loopback address raises `OfflineViolation` and is logged (logger `offline`); the probe is skipped in that mode. `tests/test_offline.py` includes a static scan of the app code for non-localhost URLs.

### Demo fixtures (`fixtures/demo/`, `dosing/demo.py`, `docs/DEMO_SCRIPT.md`)
Three synthetic patients as JSON (quiz answers by graph node id, the check to run, the expected status of each run). `demo.record(key)` replays the answers through the real `IntakeSession`. `DEMO_MODE=1` (also turns on `DOSING_DEMO_MODE` behaviour: unverified rules computed, red banner) shows **Load demo patient** for doctors on the Doctor and Dosage check pages; it saves the record and selects it. `demo.run_fixture(key)` runs the fixture through `service.evaluate_for_record` (audit written). `scripts/reset_demo_data.py` removes the demo records and demo audit entries; the audit log is one hash chain, so if other patients' entries remain the log is left alone unless `--rechain-others` is given.

### Result card (`intake/ui/result_card.py`)
Headers: *Dose ready for doctor review* (ok), *More information needed* (needs_input), *Blocked: safety rule* (blocked), *Refused: no data for this case* (refused), each with a one-sentence reason, the rule type or missing inputs, and (blocks) source id, name and link. `needs_input` lists each missing field once as a checklist with an inline input (number, yes/no/unsure, choice, or a rule picker); **Update and recompute** re-runs the engine in the same session. `blocked` shows the override form (category plus at least 10 characters); once recorded, a red **Override recorded** line is shown and the dose appears. On blocked and refused cards the UI hides dose ranges, regimen text, plan, duration and calculation steps. Display only: no dosing rule changed.

### Audit-log viewer (`intake/ui/audit_log.py`, `dosing/audit_view.py`)
Doctor-only, read-only page. Table newest first (time, doctor, patient, drug, status, action: evaluated / confirmed / override / history-check answered), filters (patient, drug, action, date range), a row expander with inputs, provenance, steps, warnings, interactions, blocks, sources and the override category and reason, and JSON/CSV export of the visible rows. "Chain verified" / "Chain broken" comes from `audit.verify()`, which recomputes every hash.

### Scanned prescriptions in interaction checks (`dosing/ocr_meds.py`)
Medicine names come only from timeline entries that carry `confirmedBy` (the OCR panel adds that when the doctor clicks Confirm); OCR parsing is unchanged. Names go through `med_synonyms.json` and join `PatientContext.ocr_meds` with provenance `ocr_doctor_confirmed` and a link `timeline[i]` plus the scan date. `PatientContext.all_meds()` merges them with self-reported medicines, de-duplicated (a medicine in both sources keeps one entry that lists both). Interactions that involve a scanned medicine carry "from scanned prescription (date)" in their `with` text and `origins`. Names the table does not know are warned as "unparsed from prescription: doctor to review", never dropped. A doctor-typed medicine list replaces the self-reported list only; confirmed scan medicines stay.

### Acknowledging unchecked contraindications
Free-text contraindications the engine cannot evaluate (dehydration, dengue, past cholestatic jaundice and similar) stay warnings. The result lists them in `acknowledge_items`. The panel shows an "I have checked these" tick-box, and Confirm stays disabled until it is ticked (`service.can_confirm(res, acknowledged)`). The ticked items are stored in `DosingCheck.acknowledgedItems` and in the audit entry. Whether any should hard-block is a clinician decision.

### Decisions recorded
* NSAID heart wording stays exactly as in the formulary. Adding stroke / cerebrovascular disease must be a clinician-reviewed addition to the formulary (with source and note), not a code change.
* Cetirizine at 12 y: both rules give 10 mg/day; the earlier rule is the default and the doctor may pick either.
* Override category plus 10 or more characters is a prototype rule. A real product needs a reviewed reason list and periodic override audits.
* Growth tables are still to be supplied (WHO CGS 0-5 y, WHO 2007 5-10 y, IAP 2015 5-18 y, a cited adult range); the draft table stays active meanwhile.

### Running the demo on a new machine
`./run_demo.sh` (or `python3 scripts/run_demo.py`) runs `scripts/startup_check.py` (Python, packages, formulary, quiz graph, a dosing self-test, logins, Ollama and the OCR model), creates a one-time `demo` doctor login and three synthetic patients if none exist, then starts Streamlit. A missing Ollama or model is only a warning: OCR scan is unavailable, everything else works. Flags: `--demo-mode`, `--port`, `--no-seed`, `--check-only`.
