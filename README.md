# OCR module (Qwen3-VL via local Ollama) - Streamlit MVP

Offline only: the one network call is to `localhost:11434`. Synthetic data only. AI drafts, the doctor confirms.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                       # optional; defaults work
.venv/bin/python scripts/make_fixtures.py  # 3 synthetic Rx + 1 lab report -> fixtures/
.venv/bin/python scripts/ocr_smoke.py      # real model, per-field PASS/FAIL + latency
.venv/bin/python -m pytest                 # unit + localhost-only + fake-Ollama e2e
.venv/bin/streamlit run app.py             # review UI
```

| Piece | File |
|---|---|
| `extract()` / `health()` (the "endpoints") | `ocr/service.py` |
| VLM prompt constant | `ocr/prompt.py` |
| Schema (pydantic) + `format` JSON schema | `ocr/schema.py` |
| Frequency parser, fuzzy matcher, needsReview | `ocr/frequency.py`, `ocr/formulary.py`, `ocr/postprocess.py` |
| Temp image lifecycle | `ocr/session.py` |
| Formulary seed (15 generics) | `data/formulary.json` |

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
.venv/bin/streamlit run intake_app.py                # pages: Patient, Staff, Doctor
```

| Piece | File |
|---|---|
| Question graph (data) | `data/intake_graph.json` (pydantic: `intake/models.py`) |
| Condition language | `intake/conditions.py` (equals, in, gte, lte, all, any, not, answered, unanswered) |
| Pure engine | `intake/engine.py`: `next_node`, `recompute_path`, `validate_graph` |
| Red-flag rules (DRAFT) | `data/red_flags.json`, `intake/redflags.py` |
| Record + local JSON store | `records/schema.py`, `records/build.py`, `records/store.py` (folder `data_local/`, gitignored) |
| Doctor summary, edit tracking | `intake/summary.py`; optional local-LLM paragraph `intake/llm_summary.py` |

Answer semantics: **"Not sure" (`unsure`) is an answer; skipped (`__skipped__`) is not.** Both continue the flow and both put the item in `dosingInputs.missing`. "Not sure" never matches a concrete value in any rule.

Red flags: all 10 rules are drafts with `source: null`, `sourceChecked: false`; the UI labels them "Draft rule, source check pending". Fill sources (WHO IMCI, ICMR STW) yourself, then set `sourceChecked: true`. Severities are placeholders too.

The optional AI paragraph (Doctor page, off by default) uses Ollama on localhost (`INTAKE_LLM_MODEL`, default `qwen3:8b`). It sees a number-free fact sheet; output containing digits, dose words or diagnostic language is discarded and the template is shown.

## Translations need native review
Every node's Hindi and Marathi (and the red-flag patient messages, and `intake/ui/strings.py`) is **machine-drafted, needs native review**. Not reviewed. Nodes: consent, age_years, age_months, sex, pregnancy, preg_bleeding, weight_kg, allergies, allergy_other, meds_any, meds_list, kidney, liver, diabetes, hypertension, asthma, chief_complaint, other_text, fev_site, cb_site, body_map_radiation, fev_onset, fev_course, fev_temp, fev_assoc, fev_relieve, fev_severity, cb_main, cb_onset, cb_rest, cb_sputum, cb_assoc, cb_pattern, cb_severity, cb_relieve, ab_site, ab_onset, ab_character, ab_assoc, ab_pattern, ab_severity, ab_relieve, hd_site, hd_onset, hd_character, hd_worst, hd_assoc, hd_course, hd_severity, hd_trigger, hd_relieve, cp_site, cp_onset, cp_char, cp_assoc, cp_course, cp_exac, cp_relieve, cp_severity, danger_signs, hx_fever, hx_cough, hx_abdomen, hx_head, hx_chest, hx_similar. Also every region label in `data/body_regions.json` and the body-map special options.

## Body map (Site and Radiation questions)
Node type `body_map`: tappable front/back outline, multi-select up to `maxSelections`, always with "I'm not sure" and "I'd prefer to tell the doctor" (radiation also "It does not spread"; fever/cough site also "No particular place"). Used by `fev_site`, `cb_site`, `ab_site`, `hd_site`, `cp_site` and the shared `body_map_radiation` (chest and abdominal pain).

- **Regions and artwork:** `data/body_regions.json`: 54 stable region ids, own plain polygons (no third-party art), en/hi/mr labels, all machine-drafted. **`right`/`left` are always the patient's own side**: on the front view the patient's right is on the viewer's left; on the back view it is on the viewer's right. The diagram says "Patient's right" / "Patient's left".
- **Stored answer:** `{regions, view, inputMode: "map"|"list"}` (+ `special` for tell-doctor / none). "I'm not sure" is the ordinary `unsure` answer. The map and the list both go through `bodymap.make_answer`: same regions give the same `regions` and `view`, in catalog order; only `inputMode` records which input was used. Record: `socrates.site = {regions, view, inputMode}`, `socrates.radiation = {regions}`.
- **Conditions:** `regionsAny` and `regionsAll`. The chest-pain rule now reads: chest pain and (sweating, or chest_left/chest_center with spread to a shoulder/arm/hand, jaw or neck). Still a draft: `source: null`, `sourceChecked: false`.
- **Offline UI:** a tiny local Streamlit component (`intake/ui/bodymap_component/index.html`, no CDN, no packages) only reports the tap position; Python resolves it with point-in-polygon (`hit_test`, with a 4-unit slop for fingers). A checkbox list of the same regions is always available.
- **Doctor page:** regions in words in the doctor's language (en/hi/mr selector), plus small highlighted diagrams (site red, radiation orange).
- **Future work (not built):** child/other body-type variants, 3D, any inference from body location.
