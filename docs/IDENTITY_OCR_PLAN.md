# Plan: patient identity and patient-side document scan

Branch `feat/patient-identity-ocr` (from `rebuild-fastapi-react`). `dosing/` is not touched. Offline only.

## What already exists and is reused
- OCR: `ocr/service.extract` (local Qwen3-VL through Ollama), `ocr/postprocess.enrich` (confidence, `needsReview`), `ocr/imageprep`, `ocr/session` (temp images). No second OCR is built.
- Store: `records/store` (one JSON per visit token `PT-XXXXXX`), `api.deps.WRITE_LOCK`, atomic writes. Patients get a sibling folder `data_local/patients/` written by the same pattern under the same lock.
- Kiosk: `api/routers/kiosk.py`, `api/sessions.py` (per-visit `X-Kiosk-Key`), React `web/src/kiosk/`.
- Doctor path to the dosing engine: only `TimelineEntry` with `source == "ocr"` and `confirmedBy` (`dosing/ocr_meds.py`). The new "Use as current medicines" action writes exactly such an entry, so nothing in `dosing/` changes.
- Audit: hash-chained `data_local/audit/dosing_audit.jsonl`.

## Decisions that differ from the prompt (reasons)
1. **Audit**: `dosing/audit.write` accepts only four dosing events and lives in `dosing/`. A new `records/identity_audit.py` appends identity, consent, lock, reset and scan events to the same file with the same chain recipe (imports `dosing.audit` helpers, does not edit them), so "Chain verified" still holds. Entries carry masked values only.
2. **Welcome back** shows the masked identifier and last visit date, not a first name: the system collects no name (CLAUDE.md: pseudonymous records).
3. **Scan endpoints** are session-scoped (`/api/kiosk/sessions/{token}/scans...`) so the existing per-visit kiosk key and the identity token are both checked.
4. **One consent**: the identity consent screen is the consent. After login/register the server answers the quiz's `consent` node with `agree` for that visit. "No thanks" goes to the existing quiz consent as an anonymous walk-in (no identifier, no scans stored).
5. **OCR progress** is stage-based plus a real streamed token count from Ollama (not a fake percentage).
6. **PIN reset** by staff generates a random temporary 4-digit PIN shown once to staff (never stored in plain, never logged).

## Backend
- `records/identity.py`: normalise, mask, Fernet encrypt, HMAC lookup hash, key from `IDENTITY_MASTER_KEY` or gitignored `data_local/identity.key`; PIN = argon2id over HMAC-peppered `(lookup hash, pin)`.
- `records/patients.py`: `Patient` model + store. `api/identity_provider.py`: `IdentityProvider` interface, `PinProvider`, stub `OtpProvider`.
- `api/routers/identity.py`: `/api/kiosk/identify|register|login|walk-in`, `/sessions/{token}/bind`, `/sessions/{token}/end`. Signed idle-expiring identity token (`X-Kiosk-Identity`, 15 min idle). Per-identifier and per-device rate limits, 5 wrong PINs lock 10 minutes.
- `api/scan_jobs.py`, `api/routers/kiosk_scans.py`: upload, background job, progress (poll plus SSE), PATCH correct, confirm, DELETE, image.
- Staff: lookup, masked view, reset PIN, complete walk-in. Doctor: visit scans (image + unverified text), previous visits, use-as-current-medicines.
- `PatientRecord` gains optional `patientId`, `identifierType`, `identifierMasked`, `returning`, `kioskScans` (old records still load, tested).

## Kiosk UI
Step indicator (1/2/3) after language. Identify A-D (method tiles, number pad, PIN pad, consent), Scan (camera/upload, real progress, cards with low-confidence marigold rows), then the existing quiz. 60 s idle with 10 s visible countdown, clears identity and unconfirmed scans. Token slip gets "Papers added" and masked identifier.

## Tests
Python: registration, login, lockout, reset, consent declined, hash/encrypt round trip, token isolation, masking, OCR lifecycle with a fake backend, OCR unavailable, audit entries, plaintext scan of data files and logs. Vitest: pad, validation, PIN logic. Playwright: full paths at 3 viewports in en/hi/mr, axe on each new screen, screenshot spec that fails on blank captures.

## Phases (a commit each)
1 plan; 2 patients store/crypto/PIN/consent/session; 3 scans/jobs/staff/doctor; 4 kiosk Step 1; 5 kiosk Step 2, indicator, idle, slip; 6 staff/doctor UI + polish + screenshots; 7 docs (CONTEXT, CLAUDE hard rules, .env.example, SECURITY).
