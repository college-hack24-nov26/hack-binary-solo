# Demo script (about 4 minutes)

Synthetic patients only. **Prototype data, not clinically verified**: say so in the first sentence. Expected results below were taken from running the fixtures (`fixtures/demo/*.json`) through the real dosing service on 2026-11-04, not typed from memory. Re-check them with `.venv/bin/python scripts/dosing_demo.py` if the formulary changes.

## Before you start (once, 2 min)
```bash
.venv/bin/python scripts/create_user.py dr_demo doctor        # once
.venv/bin/python scripts/reset_demo_data.py                   # clears the demo records and demo audit entries
DEMO_MODE=1 .venv/bin/streamlit run main_app.py               # add OFFLINE_STRICT=1 to make any outside call fail loudly
```
`DEMO_MODE=1` shows **Load demo patient** (doctor role only) and puts the red "DEMO - UNVERIFIED DATA" bar on every dosing result.
Optional: start Ollama (`ollama serve`) so the badge shows the local model server as reachable. The dosing steps below do not need it.

## Click-through

| Time | Say | Do | Expected |
|---|---|---|---|
| 0:00 | "Everything runs on this laptop. Prototype data, not clinically verified; the doctor decides." | Sign in as `dr_demo`. | Badge at the top: **Offline mode: no internet used**. |
| 0:20 | **Demo: turn Wi-Fi off now.** "Watch the badge." | Turn Wi-Fi off. Open **Network details** under the badge. | Within 30 s: **Internet: unreachable** (it was amber "reachable (not used by this app)" while Wi-Fi was on). Allowed target: `localhost:11434` (local model server); data folder listed. |
| 0:50 | "Three synthetic patients. No quiz or scan wait: I load one." | **Doctor summary** page, **Demo patient** box: pick *Demo Patient A*, click **Load demo patient**. | Green "Loaded Demo Patient A (PT-DEMOA2)". Patient is selected. |
| 1:00 | "A 4-year-old, 16 kg, fever. Paracetamol, weight-based." | Open **Dosage check** (sidebar). Drug **paracetamol**, indication **pain/fever**. In **History check** click *None of these apply* then *Save history answers*. Tick *Weight reported by patient is correct*. Click **Run dosage check**. | Header **Dose ready for doctor review**. Dose **200 mg = 4 mL of oral liquid 250 mg/5 mL**, every 6 h, daily total 800 mg, daily max 960 mg. Steps show 10 to 15 mg/kg x 16 kg. Red DEMO bar. |
| 1:50 | "Next: adult with diabetes and kidney disease. No creatinine yet. The tool will not guess." | **Doctor summary** (or this page), load *Demo Patient B*; drug **metformin**, indication **type 2 diabetes**. History check as above. Tick weight box, **Run dosage check**. | Header **More information needed**: "2 items must be filled in…", checklist: `selected_rule_id` (rule picker) and `scr_mg_dl`. No dose shown. |
| 2:20 | "I fill it in right here; no page reload." | In the checklist pick rule **metformin#0**, type creatinine **1.0**, click **Update and recompute**. | Header **Dose ready for doctor review**. Step: "CKD-EPI 2021 eGFR = 87.24". Titration plan (start 500 mg twice daily or 850 mg once daily, max 2550 mg/day): metformin has no single computed dose. Interaction warnings for Glycomet (duplicate biguanide). |
| 2:50 | "Now a patient with a penicillin allergy. Amoxicillin." | Load *Demo Patient C*; drug **amoxicillin**, indication **community-acquired pneumonia**. History check as above. **Run dosage check**. | Header **Blocked: safety rule**. Reason "Contraindication: Serious penicillin/beta-lactam allergy". Sources S4, S29, S30, S3 with links. **No dose anywhere**; calculation steps say "Hidden until an override is recorded". |
| 3:15 | "A doctor can override, but must say why." | Category **Benefit outweighs risk**, reason `short`, click **Record override and show dose**. Then reason `Mild reaction only; ID consult done`, click again. | First try: "Write a reason of at least 10 characters." Second: red **Override recorded** line; dose **750 mg = 3 x capsule 250 mg**, 3 doses/day, daily total 2250 mg. |
| 3:35 | "Every step is in a tamper-evident log." | **Audit log** page (doctor only). | **Chain verified**. Newest first: override, evaluated, history-check rows. Open the override row: category, reason, inputs with provenance, steps, sources. Filter by patient `PT-DEMOC2`; show JSON/CSV export. |
| 3:55 | "Turn Wi-Fi back on if you like; nothing changed." | Wi-Fi on. | Badge turns amber **Internet: reachable (not used by this app)**. |

## Optional: interactions from a scanned prescription (30 s)
Sign in, **Patient** page, scan the synthetic `fixtures/rx_01.png` (needs Ollama), confirm it, then check metronidazole for that patient: a confirmed scan containing warfarin shows "from scanned prescription (date)" on the interaction; an unconfirmed scan adds nothing.

## If the local model server is slow
Skip scanning and the quiz entirely. **Load demo patient** uses pre-saved answers (the three JSON fixtures) and goes through the normal doctor screens, so the dosing, override and audit steps above need no model. The existing kiosk **demo** button on the Patient page is a second pre-filled patient (chest pain).

## Rerun
`.venv/bin/python scripts/reset_demo_data.py` removes the demo records and demo audit entries. If audit entries of other patients share the log it leaves the log alone; pass `--rechain-others` to remove the demo rows anyway (this re-computes the remaining hashes).

## Known limits to say out loud
All formulary data is `verified: false`; the demo bar says so. Hindi/Marathi text is machine-drafted. Fixtures carry a display name ("Demo Patient A") only in the demo box: patient records have no name field.
