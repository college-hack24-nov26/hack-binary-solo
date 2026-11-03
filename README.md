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
