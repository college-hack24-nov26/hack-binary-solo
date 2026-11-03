# Dosage-check logic

Decision support for registered doctors. The doctor decides. **Prototype data, not clinically verified**: every formulary drug is `verified: false`.
Code: `dosing/` (engine), `intake/ui/dosing_panel.py` (doctor screen). No LLM, no network, no randomness; same input gives byte-identical output.

## Status values
`blocked` (unoverridden hard stop) > `refused` (no rule / unknown drug / UNVERIFIED rule with `DOSING_ALLOW_UNVERIFIED` off / incomplete rule) > `needs_input` (a missing fact, listed with why) > `ok`.
Number fields are blanked unless the status is `ok` (or `needs_input` for product choice, where the closest options are listed).
A result is `final` only when status is ok, a number was computed and weight (and creatinine, when a renal measure was used) is doctor-entered or doctor-confirmed.

## Config
`DOSING_ALLOW_UNVERIFIED` (default false), `DOSING_ML_STEP` (0.5), `DOSING_ABW_FACTOR` (default: formulary `factor_default`), `DOSING_FORMULARY_PATH`. Override reason minimum length: 10 characters (`Config.override_min_chars`).

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
