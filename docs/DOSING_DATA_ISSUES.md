# Dosing data issues (formulary v0.2.0). The formulary was not modified.

## Structure and ambiguity
1. Rules have no ids; the engine uses `drug#index` plus a content hash. Reordering the file changes ids.
2. `population: {}` has no stated meaning. Used as paediatric when weight-based; metformin prediabetes (fixed 500 mg bid) has `{}` and no age.
3. `max_age_*` semantics conflict: cetirizine 2-6 then 6-12 and amoxicillin-clavulanate max 3 months / min 3 months read as exclusive; metronidazole `max_age_years: 17` reads as inclusive. Engine: inclusive through the completed unit, so boundary ages return both rules.
4. Weight bounds: ibuprofen 20-29 kg leaves a gap above 29 kg; `max_weight_kg` 40 (exclusive) vs doxycycline 45 / 45.5 (inclusive in the source labels).
5. Indication labels are free text with source tags; the same clinical indication appears under several labels ("pain/fever", "fever (India)"), and labels like "adult (Ghana FDA...)", "paediatric (...)", "general" are not indications.
6. Several rules overlap for the same patient (paracetamol adult: 4+ rules; amoxicillin child: WHO 80-90 vs ICMR 30-40 vs US label). `defaults.amoxicillin_child` says "doctor picks".
7. Dose rules with `options` mix shapes: free-text strings (not computable), dict options (amoxicillin-clavulanate), and ondansetron rule 10 carries both `dose_mg` and string options.

## Missing or incomplete fields
8. Doxycycline rule 14 (`mg_per_kg_per_day`) has no value. Ondansetron rule 7 (IV post-operative, `mg_per_kg_per_dose`) has no `mg_per_kg`. Both are refused.
9. Cap-only rules (amoxicillin <12 weeks 30 mg/kg/day, diclofenac Ghana, ibuprofen inflammatory 40): the doctor must enter the intended mg/kg/day.
10. Amoxicillin WHO weight bands stop at 20 kg ("band unclear" in the note); no extrapolation, refused above.
11. No scored-tablet flag anywhere (cetirizine "half tablet" appears only in a note). Whole tablets only.
12. Pantoprazole `forms_india` lists only an injection although the rules are oral. Oral doses return `needs_input` (no listed product).
13. Amoxicillin-clavulanate rule 1 names an 875/125 tablet and rule options name 400/57 and 250/62.5 products that are not in `forms_india`; rule 5 (ES-600) gives no ratio.
14. Contraindications, warnings, pregnancy, hepatic and drug-level interaction entries are free text. They are mapped by `dosing/data/safety_map.json`; unmapped items surface as "doctor to confirm" (e.g. dehydration, dengue, past cholestatic jaundice, quinolone hypersensitivity).
15. Several interaction `b` fields hold lists with qualifiers ("disulfiram (within 2 weeks), alcohol", "aspirin (except low-dose ...)"); qualifiers are ignored by matching.
16. One top-level interaction has a mixed status string ("VERIFIED for ondansetron; others UNVERIFIED"); treated as UNVERIFIED.
17. No Child-Pugh class-to-score mapping: ondansetron uses a score, metronidazole a class, so both may be requested.
18. Renal: `GFR` and `CrCl` rows are evaluated with Cockcroft-Gault (formulary `unit_rule`); no formula exists for CrCl in children or for ages 16-18 (eGFR via Schwartz stops at 16). Cetirizine has overlapping eGFR/CrCl rows with conflicting contraindication thresholds. Ciprofloxacin has no band below CrCl 5. Renal action text is only parsed when it reads "N mg every H h / once daily".
19. Defaults: `defaults.paracetamol_child` / `ibuprofen_child` keys are named differently from rule keys (`max_mg_per_kg_per_day` vs `max_per_kg_per_day`); mapped by the engine.
20. Asthma and diabetes warnings exist only for some NSAIDs; same-class text is borrowed and labelled.
21. UNVERIFIED rules (cetirizine 0-2) duplicate VERIFIED ones and are merged away. Outdated labels flagged in `meta.changelog` are used as-is.
22. Formula IBW is UNVERIFIED and no rule says when to use IBW/ABW instead of actual weight; Cockcroft-Gault uses actual weight.
23. No G6PD text anywhere; the field is shown only.
24. The weight plausibility table (`dosing/data/plausibility.json`) and the medicine synonym table are engine-side drafts without sources.
