# Security notes: patient identity and scanned papers

Prototype for an offline clinic. Nothing here has had a security audit, and nothing is claimed to meet any standard or regulation.

## What is stored, where
| Data | Where | How it is protected |
|---|---|---|
| Mobile number or ABHA number | `data_local/patients/PID-*.json` (`identifierEnc`) | Fernet (AES-128-CBC + HMAC) with a key derived by HKDF from the master key |
| Lookup of "is this number known" | same file (`lookupHash`) | HMAC-SHA256 of `type:normalised number`, keyed from the master key (a leaked file cannot be brute-forced offline without the key) |
| 4-digit PIN | same file (`pinHash`) | argon2id (library defaults) over `HMAC(pepper, lookupHash:pin)`; never stored or logged in plain; 5 wrong tries lock the record for 10 minutes (persisted) |
| Master key | `IDENTITY_MASTER_KEY` env var, or `data_local/identity.key` (0600, created on first use, inside the gitignored data folder) | Losing it makes stored identifiers unreadable; backing it up and the data folder separately is the operator's job |
| Consent records | patient file (`consents[]`: version, language, time, kiosk id, what was agreed) | |
| Visit answers, masked number, scan text | `data_local/records/PT-*.json` | Masked values only (`+91 ••••• ••321`, `91-••••-••••-1234`); no full number |
| Scan pictures | `data_local/scans/<random id>.jpg` (0600) | Random file names, EXIF/GPS stripped; `KIOSK_SCAN_KEEP_IMAGE=0` deletes the picture when the patient confirms |
| Audit | `data_local/audit/dosing_audit.jsonl` (hash chain) | Identity, consent, lock, PIN reset, scan and doctor-use events; masked values and ids only |

Files in `data_local/` are protected only by the operating system account and disk encryption of the clinic computer. Data at rest is not encrypted apart from the identifier.

## Access
- The kiosk identity token (`X-Kiosk-Identity`, HMAC-signed id, 15 minutes idle, cleared on Finish, on the token slip and on reset) opens only `/api/kiosk/...` routes for the visit it is bound to. Staff and doctor routes read the login cookie, so this token opens none of them; another patient's visit looks like it does not exist (tested).
- Per-device and per-number rate limits on identify, register and login (in memory; the PIN lock is persisted).
- Staff see masked numbers only. Staff can reset a PIN (a random temporary PIN is shown once to the staff member) and complete a walk-in; both are audited.
- The doctor sees scanned pictures and text labelled "Patient-supplied, unverified text". Only the doctor action "Use as current medicines" copies items into the dosage context, each with provenance and the doctor's name.

## What is not claimed
- No OTP and no identity "verification": the PIN only proves the person knows the PIN they chose (or that staff gave them). A 4-digit PIN is weak by nature; the lock and rate limits are the mitigation.
- ABHA numbers are checked for format only (14 digits). Nothing is looked up or verified, and no government service is contacted.
- No claim of compliance with any law or standard, and no statement that the data are "secure". The consent text states only what is kept, who sees it, why, and that it can be removed at the desk.
- Removing a patient at the desk is not built yet (open item): the consent text promises it, so staff need a procedure until it exists.
- Scan reading is done by a local vision model and can be wrong; the patient check and the doctor check are the safeguards.
- Offline: no code added here calls the network (`OFFLINE_STRICT=1` passes). The only outbound target stays the local model server on `localhost`.
