# Demo script (about 4 minutes)

Synthetic patients only. **Prototype data, not clinically verified**: say so in the first sentence. Expected results below were taken from running the fixtures (`fixtures/demo/*.json`) through the real dosing service with `scripts/dosing_demo.py` on 2026-11-04, not typed from memory, and are checked by `web/e2e/doctor.spec.ts`. Re-check them with `.venv/bin/python scripts/dosing_demo.py` if the formulary changes. A 43-second video of the judge path is in `docs/screens/demo.webm`.

## Before you start (once, 2 min)
```bash
.venv/bin/python scripts/create_user.py dr_demo doctor        # once (doctor1 is linked to Dr. Asha Kulkarni in data/doctors.json)
.venv/bin/python scripts/reset_demo_data.py                   # clears the demo records and demo audit entries
DEMO_MODE=1 .venv/bin/python scripts/run_server.py            # add OFFLINE_STRICT=1 to make any outside call fail loudly
```
Open three windows on `http://localhost:8000`: the **tablet** at `/kiosk` (or a real tablet on the LAN at the address the server prints), the **staff desk** at `/staff`, the **doctor** at `/doctor`. `DEMO_MODE=1` shows **Load demo patient** (doctor) and **Add synthetic chest-pain patient** (staff board), and puts the red "DEMO - UNVERIFIED DATA" bar on every dosing result.
Optional: start Ollama (`ollama serve`) so scanning works and the badge shows the local model server as reachable. Nothing below needs it.

## Click-through

| Time | Say | Do | Expected |
|---|---|---|---|
| 0:00 | "Everything runs on this laptop. Prototype data, not clinically verified; the doctor decides." | Point at the pill in the staff/doctor header. | **Offline: no internet used**. Click it: allowed target `localhost:11434` (local model server), data folder, internet probe result. |
| 0:15 | "A patient who reads Marathi walks up to the tablet." | Tablet: tap **मराठी**, **मी सहमत आहे**, keypad 5-4 **पुढे चला**, **पुरुष**, keypad 7-2, then **छातीत दुखणे** (chest pain) and the next answers. | One big question per screen, tiles that show a check and **निवडले**, a calm progress bar with no numbers. |
| 0:45 | "Where does it hurt? Tap the body, or choose from a list." | On **वेदना कुठे आहे?** tap the centre of the chest and the left upper arm, then **पुढे चला**. On **यापैकी आणखी काही आहे का?** tap **घाम येणे** (sweating), **पुढे चला**. | Regions fill teal and appear as chips in Marathi; "Patient's right / left" under the figure. After the sweating answer a calm card says to tell the staff. No rule id, no diagnosis. |
| 1:10 | "Meanwhile the desk sees it, without refreshing." | Staff window. | An **Urgent** row has appeared on the board with "Draft rule, source check pending" and the triggering answers (Sweating, Chest centre, Upper arm, patient's left); a soft chime if the desk has clicked once since loading (browsers block sound before that) and sound is on. |
| 1:25 | "Back to the patient: check the answers, choose a doctor." | Tablet: finish the questions, **सर्व बरोबर आहे**, choose **Dr. Asha Kulkarni**. | A token slip like the paper parchi: queue number, token `PT-…`, doctor, **खोली 12**, a green floor-line stripe and **हिरव्या रेषेने खोली 12 कडे जा**, then "You are here > > > Room 12". The tablet clears itself after 60 s (or **झाले**). |
| 1:50 | "A child with fever. Paracetamol, weight-based." | Doctor: sidebar **Load demo patient**, *Demo Patient A* **Load and open dosage check**. In **History check** click *None of these apply*, then *Save history answers*. Tick *Weight reported by patient is correct*. **Run dosage check**. | **Dose ready for doctor review**. **200 mg** = **4 mL of oral liquid 250 mg/5 mL**, every 6 h; daily total 800 mg, daily maximum 960 mg. The ruler shows the rule range 160 to 240 mg with the 200 mg marker, and 800 of 960 mg per day. Red DEMO bar. Steps (10) in the disclosure. |
| 2:25 | "Adult with diabetes and kidney disease. No creatinine yet. The tool will not guess." | **Load demo patient** *B*; metformin / type 2 diabetes are pre-selected. History check as above, tick weight, **Run dosage check**. | **More information needed**: "2 items must be filled in…": `selected_rule_id` (rule picker) and `scr_mg_dl`. No dose, no ruler, no plan. |
| 2:45 | "I fill it in right here." | In the checklist pick **metformin#0**, type **1.0**, **Update and recompute**. | **Dose ready for doctor review**. Step "CKD-EPI 2021 eGFR = 87.24". Titration plan: start 500 mg twice daily or 850 mg once daily, maximum 2550 mg a day. Interaction lines for Glycomet. |
| 3:05 | "Now a penicillin allergy. Amoxicillin." | **Load demo patient** *C*; History check as above, **Run dosage check**. | **Blocked: safety rule**. "Contraindication: Serious penicillin/beta-lactam allergy". Sources S4, S29, S30, S3. **No dose anywhere**; steps say "Hidden until an override is recorded". |
| 3:25 | "A doctor can override, but must say why." | Override form: category **Benefit outweighs risk**, reason `short`, **Record override and show dose**; then `Mild reaction only; ID consult done`, click again. | First: "Write a reason of at least 10 characters." Second: red **Override recorded** line; **750 mg** = **3 × capsule 250 mg**, 3 doses a day, daily total 2250 mg, ruler 500 to 1000 mg. |
| 3:45 | "Every step is in a tamper-evident log." | Sidebar **Audit log**. | **Chain verified** seal; newest first: override, evaluated, history rows, each hash linked to the previous one. Open the override row: category, reason, inputs, provenance, steps, sources. Filter patient `PT-DEMOC2`; **JSON** / **CSV** export. |

## Optional: scanned prescription (30 s, needs Ollama)
Staff desk: open a patient, **Take a photo or choose an image** (`fixtures/rx_01.png`), tick consent, **Read and send to doctor**. Doctor: patient **Timeline** tab shows the draft with the image; edit if needed, **Confirm and attach to patient**. A Dosage check for metronidazole then shows the warfarin interaction "from scanned prescription (date)". Unconfirmed scans add nothing. Without Ollama, the upload says plainly that scanning is unavailable and everything else keeps working.

## If something is slow
Skip the kiosk entirely: **Load demo patient** uses pre-saved answers replayed through the real intake session, so the dosing, override and audit steps need no tablet and no model. **Add synthetic chest-pain patient** on the staff board gives a red-flag patient in one click.

## Rerun
`.venv/bin/python scripts/reset_demo_data.py` removes the demo records and demo audit entries. If audit entries of other patients share the log it leaves the log alone; pass `--rechain-others` to remove the demo rows anyway (this re-computes the remaining hashes).

## Known limits to say out loud
All formulary data is `verified: false`; the demo bar says so. Hindi/Marathi text is machine-drafted, needs native review. Fixtures carry a display name ("Demo Patient A") only in the demo loader: patient records have no name field. The wait time on the slip is an estimate (patients ahead x 10 min).
