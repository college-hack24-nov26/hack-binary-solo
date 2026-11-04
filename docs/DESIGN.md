# Design: MediKiosk OPD (kiosk, staff desk, doctor workstation)

Written before any UI code. The tokens below are the single source for `web/src/styles/tokens.css`; change them here first, with a reason.

## 1. Concept (three sentences)

The kiosk is public signage that listens: one big question at a time in the patient's own script, tiles that feel like large printed buttons, and a token slip that is a clean modern *parchi* with the painted floor line that leads to the doctor's room.
The staff desk and doctor workstation are quiet clinical instruments (ink on cool paper, borders not shadows, dense tables) where only three things are loud: the patient's own words, the safety state, and the dose.
Colour always means something and never decorates: teal acts, red stops, green confirms, marigold asks for attention, and each room owns exactly one floor-line colour.

## 2. Users and what the design must do for them

| User | Context | Design consequence |
|---|---|---|
| Patient (elderly, semi-literate, anxious, shared tablet) | Standing at a tablet in a noisy OPD, often in Marathi or Hindi | One question per screen; question text 36-44 px in Devanagari; 64 px+ targets; "Not sure" is a first-class answer; calm progress bar with no numbers; never shows anything clinical; resets itself |
| Desk clerk (peak time, many patients) | Laptop at registration, interrupted constantly | Urgent red flags pinned and announced once; live updates without reload; vitals form keyboard-first; one sticky search |
| Doctor (between patients) | Laptop in a consulting room | Patient's words and safety state first; dose shown only when the engine says ok; numbers in tabular figures; every override reason visible; audit chain status at a glance |

## 3. Tokens

### 3.1 Palette (light)

| Token | Hex | Use |
|---|---|---|
| `ink` | #14302D | All body text and icons (instead of black) |
| `teal` | #0B5A55 | Primary actions, brand, focus ring, selected tiles |
| `paper` | #FAFBF8 | Page background (cool, not cream) |
| `surface` | #FFFFFF | Panels and tiles on paper |
| `tint` | #E3F0EE | Selected/quiet surfaces, chips, table header |
| `line` | #C9D6D3 | Borders, dividers (non-text) |
| `muted` | #4F6461 | Secondary text, captions |
| `marigold` | #F2B33D | Attention fills (help banner, pending scans, demo-only notices), always with ink text, never as text |
| `marigold-tint` | #FDF3DC | Quiet attention surface |
| `red` | #B42318 | Urgent and blocked only (red flags, blocked header, override recorded, chain broken) |
| `red-tint` | #FDECEA | Surface behind urgent/blocked content |
| `green` | #1C7A4C | OK and confirmed only (dose ready, chain verified, saved) |
| `green-tint` | #E6F4EC | Surface behind ok content |

### 3.2 Palette (dark, staff and doctor only, designed not inverted)

Dark is a deep teal-black, not grey, so the brand survives; surfaces step up in lightness instead of using shadows; red and green are lifted to keep contrast, not just brightened.

| Token | Hex |
|---|---|
| `paper` | #0F1E1C |
| `surface` | #16302C |
| `tint` | #1D3B36 |
| `line` | #2C4A45 |
| `ink` | #E6EFED |
| `muted` | #9DB5B0 |
| `teal` | #5CC4B8 (text on teal fills uses `paper` #0F1E1C) |
| `red` | #FF8F85 (fills use #7A1A12 with ink text). Changed from #F97066 after axe: that red was 4.35-4.5:1 on dark tint/green surfaces |
| `green` | #4ADE9B |
| `marigold` | #F2B33D (with #0F1E1C text) |

### 3.3 Contrast table (computed, WCAG 2.x relative luminance)

| Pair | Ratio | Passes |
|---|---|---|
| ink on paper | 13.57 | AAA |
| ink on tint | 12.05 | AAA |
| teal on paper | 7.75 | AAA |
| white on teal (primary button) | 8.05 | AAA |
| teal on tint (selected tile label) | 6.89 | AA |
| muted on paper | 6.08 | AA |
| muted on tint | 5.40 | AA |
| red on paper | 6.33 | AA |
| white on red | 6.57 | AA |
| red on red-tint | 5.75 | AA |
| green on paper | 5.13 | AA |
| white on green | 5.33 | AA |
| green on green-tint | 4.70 | AA (body text only at 15 px+) |
| ink on marigold | 7.58 | AAA |
| ink on marigold-tint | 12.77 | AAA |
| marigold on paper | 1.79 | FAIL: never used for text; fills only, with a 1 px ink border when it carries meaning |
| dark: ink on paper | 14.67 | AAA |
| dark: ink on surface | 12.01 | AAA |
| dark: teal on paper | 8.21 | AAA |
| dark: muted on paper | 7.91 | AAA |
| dark: red #FF8F85 on paper / surface / green-tint / red-tint / tint | 7.79 / 6.38 / 5.68 / 6.95 / 5.50 | AA |
| dark: green on paper | 9.99 | AAA |
| dark: paper on marigold | 9.23 | AAA |

### 3.4 Floor-line colours (synthetic, in `data/doctors.json`)

Each doctor's room has one line colour. The stripe is a graphic; its name is always printed next to it ("Follow the green line"), so colour is never the only signal. Text placed **on** a stripe uses the listed text colour.

| Doctor id | Room | Line | Hex | Text on stripe | Ratio | Stripe vs paper |
|---|---|---|---|---|---|---|
| dr_general | 12 | green | #1E7B45 | white | 5.28 | 5.09 |
| dr_heart | 14 | blue | #1F5FAD | white | 6.37 | 6.13 |
| dr_child | 7 | yellow | #F2B33D | ink | 7.58 | 1.79, so the yellow stripe gets a 2 px ink edge |
| dr_women | 9 | purple | #6A3FA6 | white | 7.31 | 7.03 |

Red is deliberately not a floor-line colour: on this product red means "stop".

### 3.5 Type

One family: **Noto Sans** (Latin) with **Noto Sans Devanagari**, self-hosted from `@fontsource`. Weights used: 400, 600, 700. No second face, no italics on Devanagari (`font-synthesis: none`), no letter-spacing anywhere (no tracked caps).

Line height: body 1.5, headings 1.3 for every script, so matras and conjuncts are never clipped. Numbers that are compared or copied use `font-variant-numeric: tabular-nums` (doses, tokens, queue numbers, times, vitals).

Workstation scale (ratio about 1.2, base 15 px):

| Step | px | Use |
|---|---|---|
| `xs` | 13 | table meta, captions (minimum) |
| `sm` | 14 | table cells, form help |
| `base` | 15 | body |
| `md` | 17 | panel titles |
| `lg` | 20 | section headings |
| `xl` | 24 | page title, patient token in header |
| `2xl` | 30 | result-card header |
| `dose` | 44 | the dose figure (ok only) |

Kiosk scale (base 20 px, larger steps):

| Step | px | Use |
|---|---|---|
| `k-body` | 20 | helper text, captions (minimum) |
| `k-tile` | 24 | tile labels |
| `k-lead` | 28 | screen titles, review answers |
| `k-question` | clamp(32, 4.2vw, 44) | the question (hero), weight 700 |
| `k-queue` | 120 | queue number on the token slip |

"A+ larger text" multiplies the kiosk scale by 1.2 (applied as a root font-size change, so every rem grows together).

### 3.6 Spacing, radii, elevation, motion

- Spacing: 4 px grid; layout uses 8 px steps (`1`=4, `2`=8, `3`=12, `4`=16, `6`=24, `8`=32, `12`=48, `16`=64).
- Radii follow hierarchy, not one radius everywhere: `pill` 999 px (badges, chips, status pill); `tile` 16 px (kiosk tiles and keypad); `panel` 8 px (workstation panels, dialogs); `field` 6 px (inputs, buttons on the workstation); `slip` 2 px with a perforated top edge (the parchi).
- Elevation (three levels, borders first):
  - `0` flat: border `line` on `surface` (panels, tables);
  - `1` pressable: a 3 px bottom border in a darker tone of the tile, no blur (kiosk tiles look like keys; they sink 2 px when pressed);
  - `2` overlay: dialogs, drawer, popovers: `0 12px 32px rgb(20 48 45 / .18)`.
- Motion: `--dur-feedback` 120 ms; `--dur-screen` 240 ms; one easing `cubic-bezier(.2, 0, 0, 1)`. Under `prefers-reduced-motion: reduce` every duration becomes 0 ms and `navigator.vibrate` is not called.

## 4. Signature moments (where the boldness is spent)

1. **Kiosk question screen.** The question is the hero, set in the patient's script at 36-44 px. Tiles press in 120 ms (sink + darker), then show a check icon *and* the word "Selected" (not colour alone). Forward slides left, Back slides right; this is the only non-trivial motion on the kiosk.
2. **Body map.** Original SVG polygons from `data/body_regions.json`; front/back toggle; selected regions fill teal and appear as removable chips in the patient's language; "Choose from a list" is always one tap away; side labels say "Patient's right" / "Patient's left".
3. **Token slip (parchi).** Perforated top edge, hospital line, a 120 px queue number, doctor and room, then a thick floor-line stripe with "Follow the green line to Room 12" in the patient's language. A stamp-like check lands once, only after the server returned the slip. Print stylesheet hides everything else.
4. **Dose ruler (doctor, ok only).** A horizontal ruler drawn from engine fields only: the rule's `dose_range_mg` band, the delivered `dose_mg` marker, and a second bar for `daily_total_mg` against `daily_max_mg` with `binding_cap` named. No ruler and no figure for needs_input, blocked or refused.
5. **Audit chain.** Each row shows a short hash prefix and the previous entry's prefix joined by a link glyph; a seal reads "Chain verified" (icon + text) or "Chain broken" in red with the first bad entry highlighted.
6. **Staff board urgent row.** Enters with one attention animation (a single marigold-to-surface fade, 600 ms) then stays still; shows an icon, "Urgent", the rule's staff message, "Draft rule, source check pending" and the triggering answers.
7. **Offline badge.** A pill "Offline: no internet used" with a small live dot; opens a popover with the allowed target, local services and the public probe result, worded exactly as the server reports it.

## 5. Wireframes

### 5.1 Kiosk question (portrait 800x1280)
```
+--------------------------------------------------------------+
| [< Back]                    [Listen again] [अ Language] [Help]|
|==============================================================|  <- calm progress bar (no numbers)
|                                                              |
|  तुम्हाला ताप किती दिवसांपासून आहे?                             |  <- k-question, 700
|                                                              |
|  +----------------------------+ +---------------------------+|
|  |  आज                         | |  1-3 दिवस          [✓ निवडले]||  <- tiles, 2 columns, 96 px tall
|  +----------------------------+ +---------------------------+|
|  +----------------------------+ +---------------------------+|
|  |  4-7 दिवस                   | |  एक आठवड्यापेक्षा जास्त        ||
|  +----------------------------+ +---------------------------+|
|                                                              |
|--------------------------------------------------------------|
|  [ खात्री नाही ]                              [ वगळा ]          |  <- secondary row, separated
+--------------------------------------------------------------+
```
Landscape (1280x800): question in the left 45 %, tiles in the right 55 %, secondary row under the tiles.

### 5.2 Body map
```
+--------------------------------------------------------------+
| [< Back]                    [Listen again] [Language] [Help] |
|==============================================================|
|  Where is the pain?                                          |
|  +------------------+   Selected:                            |
|  |   [Front|Back]   |   (Chest centre  x) (Left upper arm  x)|
|  |      ( )         |                                        |
|  |     /|█|\        |   [ Choose from a list ]               |
|  |      | |         |                                        |
|  | Patient's right  |                         [ Continue ]   |
|  |   Patient's left |                                        |
|  +------------------+                                        |
|--------------------------------------------------------------|
| [ I'm not sure ]   [ I'd prefer to tell the doctor ]  [Skip] |
+--------------------------------------------------------------+
```

### 5.3 Review
```
+--------------------------------------------------------------+
|  Please check your answers                                   |
|  Age ............................ 54            [Change]     |
|  Weight ......................... 72 kg         [Change]     |
|  Main problem ................... Chest pain    [Change]     |
|  Where ...... Chest centre; Left upper arm      [Change]     |
|  ...                                                         |
|                      [ Everything is correct ]  (primary)    |
+--------------------------------------------------------------+
```

### 5.4 Token slip (parchi)
```
  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .   <- perforated edge
 +---------------------------------------------+
 |  OPD token                       04 Nov 2026|
 |                                              |
 |                 27                           |  <- 120 px queue number, tabular
 |              PT-7KQ2MD                       |
 |----------------------------------------------|
 |  Dr. Asha Kulkarni · General Physician       |
 |  Room 12 · Ground floor                      |
 |  ███████████████████████████████████████     |  <- 16 px floor-line stripe (green)
 |  Follow the green line to Room 12            |
 |  About 20 minutes (estimate) · 2 ahead       |
 +---------------------------------------------+
        [ Print slip ]        [ Done ]
```

### 5.5 Staff board (1440x900)
```
+-----------+--------------------------------------------------------------+
| Board     | [Offline: no internet used •]        [sound] [theme] [staff1]|
| Patient   |--------------------------------------------------------------|
| Scans     | ! Help requested at the kiosk by PT-4XQ2ME  [Go] [Dismiss]   |
| Help (1)  |--------------------------------------------------------------|
|           | URGENT  PT-7KQ2MD  Chest pain spreading, sweating            |
|           |  Draft rule, source check pending · Triggered by: ...        |
|           |--------------------------------------------------------------|
|           | [Search token or complaint ]  [Status v] [Doctor v]          |
|           | #  | Token    | Age/sex | Complaint | Flags | Doctor | Wait  |
|           | 27 | PT-7KQ2MD| 54 M    | Chest pain| 1 !   | Dr. A  | 12 min|
+-----------+--------------------------------------------------------------+
```

### 5.6 Doctor workstation
```
+-----------+--------------------------------------------------------------+
| My queue  | PT-DEMOA2 · 4 y F · Fever · Dr. Asha    [Offline •] [theme]  |
| Patient   |--------------------------------------------------------------|
| Audit log | [Summary][Vitals][Timeline][Notes][Dosage check][Dosing rec] |
| Demo      |--------------------------------------------------------------|
|           | Prototype data, not clinically verified                      |
|           | (section content)                                            |
+-----------+--------------------------------------------------------------+
```

### 5.7 Dose result (ok)
```
| DEMO - UNVERIFIED DATA                                       | <- red bar, only when result.demo
| ✓ Dose ready for doctor review                               |
|   Every required input is present and no safety rule stopped |
|   Rule paracetamol#2                                         |
|                                                              |
|   200 mg   = 4 mL of oral liquid 250 mg/5 mL   every 6 h      |  <- dose, 44 px tabular
|                                                              |
|   per dose  |----[=====|=========]-----|   range 160-240 mg |  <- band + marker
|   per day   |=================|.....|      800 of 960 mg    |  <- binding cap: daily max
|                                                              |
|   > Calculation steps (5)                                    |
|   [x] I have checked these   [ Confirm and save to record ]  |
```
For blocked/refused: header, reason, sources and the override form; no ruler, no numbers, steps say "Hidden until an override is recorded".

### 5.8 Audit chain
```
| [✓ Chain verified]   12,431 entries   [Export JSON] [Export CSV] |
| Time        Action     Patient    Drug        Status   Hash       |
| 15:42:10    override   PT-DEMOC2  amoxicillin ok       3fa1…  ⟵ 9be0… |
| 15:42:10    evaluated  PT-DEMOC2  amoxicillin ok       9be0…  ⟵ 41c2… |
|   v (expanded: inputs, provenance, steps, warnings, sources, override) |
```

## 6. Component inventory (all shown in `/gallery`)

Button (primary, secondary, ghost, danger-with-confirm, loading, success, icon-only with required label, toggle with `aria-pressed`), Tile (default, pressed, selected, disabled), Keypad, Scale 0-10, Body map, Chip, Field/Input with error, Select, Checkbox, Badge/Status pill, Offline badge, Red-flag row, Result card x4 statuses, Dose ruler, Audit chain row, Token slip, Empty state, Skeleton, Error state, Toast.

## 7. Self-review: generic defaults found and what changed

| Looked generic | Change |
|---|---|
| Every block an identical rounded white card with a grey shadow | Panels are flat with 1 px borders; only dialogs and the drawer get a shadow; kiosk tiles use a bottom "key" edge instead of a blur |
| One radius everywhere | Pill / tile 16 / panel 8 / field 6 / slip 2 |
| Tracked-out ALL-CAPS overlines above headings | Removed; section names are sentence case at `md` weight 600 |
| Status shown as coloured dots only | Every status has an icon and a word (Urgent, Blocked, Chain verified) |
| "Question 7 of 73" progress | A thin bar only; the path is adaptive so a count would lie |
| Success toast before the slip exists (the reference screenshot bug) | The slip header and the stamp render only from the `finish` 200 response |
| Arrows appended to button text ("Next →") | Buttons say the action ("Continue", "Run dosage check"); direction is shown by motion |
| Hero gradient on the kiosk start screen | Plain paper with three large language tiles, each in its own script |
| Numbered badges on the sidebar | Only real counts (help requests) get a number |

## 8. Review checklist (run on every screenshot set)

Hierarchy readable in three seconds; one primary action; grid alignment; no clipped Devanagari, no truncated Marathi; contrast; kiosk touch targets 64 px+; no layout shift; nothing that looks like a template; then remove one unnecessary decoration per screen and record it below.

## 9. Review log

### Review 1: /gallery, before any feature screen (Phase 1)
Captured 22 screenshots (`docs/screens/gallery/`, 4 viewports, en/hi/mr, light/dark) and section crops at 800 and 1280 px.
- Icon-only buttons showed a 6 px glyph: two padding classes fought (`px-4` vs `px-0`). Icon-only buttons now get their own size class and icons never shrink.
- The danger button's outline state was built by overriding classes; it is now its own `danger-outline` variant (no class fights).
- Warnings and interactions were a stack of identical bordered boxes, each prefixed "Warning:"/"Interaction:" (the engine text already starts with "Interaction"). Now one bordered group per kind with a count, hairline dividers and an icon per line. **Removed decoration:** the per-item boxes.
- Token slip: the date printed Devanagari digits next to Western-digit token and room numbers; dates now use Western digits in every language (`-u-nu-latn`), matching how staff read tokens aloud. The stamp overlapped "Your number"; it now sits beside the token. The perforated edge was invisible white-on-paper; the slip now lies on a tint "counter" and the perforation is larger.
- Red-flag rows printed "today?:" when the node has no short label; trailing punctuation is respected.
- Checked: Devanagari conjuncts and matras unclipped in tiles, chips and slip at 1.3-1.5 line height; selected tile shows icon + word; dark theme surfaces step in lightness, red/green lifted.

### Review 2: doctor workstation (Dosage check, summary, audit), light and dark
- Two competing primary buttons (Run dosage check and Confirm): Run is now primary only until a result exists ("Run dosage check again", secondary after); Confirm turns primary only when the server says it can be confirmed; on a blocked result the override button is the one strong action.
- The 14 "other drugs this visit" checkboxes pushed the History check below the fold: form, route, other drugs and "show every rule" now sit in one disclosure.
- The dose block split into two narrow columns and wrapped "250 mg/5 mL"; the dose now sits above a full-width ruler.
- The result jumped out of view after a run (focus scrolled it under the sticky header); it now scrolls to the result's top with a header margin, instant under reduced motion.
- "A · B" meta strings removed (daily total line, offline badge, red-flag rule line); History check no longer repeats "Drinks alcohol / Drinks alcohol?".
- Summary fields looked like a stack of form boxes with resize grips; they are now borderless auto-sizing text that shows a border on hover/focus.
- Drug name truncated in a two-column row at 1440; drug and indication stack in the left column on wide screens.
- **Removed decoration:** the teal 2 px frame around the Run section.
- Dark: surfaces step up in lightness, the DEMO bar keeps white-on-red, the chain seal stays green with text.

### Review 3: kiosk, portrait 800x1280 (Marathi) and landscape 1280x800 (Hindi)
- Type was too timid for an elderly reader: Devanagari tile labels read about 20 px. Tiles are now 28 px, the question 36-52 px, and the language screen has a hero line in English with the Hindi and Marathi lines under it, 52 px language names and the product mark.
- Body-map side labels were drawn inside the SVG at about 7 px; they are now real text under the figure ("Patient's right" / "Patient's left", swapped on the back view).
- The stamp overlapped the token; it now sits in the flow under the token and can never cover it. The slip's "Room 12 · Ground floor" and "estimate · ahead" meta strings became a comma and a line break.
- The floor line was a thin bar; it now runs edge to edge across the slip, and under the slip a full-width "You are here > > > Room 12" strip in the room's colour (text colour chosen for AA on that colour; the yellow line gets an ink edge). This is the kiosk's signature moment.
- Checked: one primary action per screen (Continue or the tiles themselves; Not sure and Skip are secondary in their own row under a dashed rule); Marathi consent text wraps without clipping at line height 1.5; landscape puts the question left and answers right.
- **Removed decoration:** the second dashed rule that separated the slip's wait line.

### Review 4: staff desk, 1440x900 light/dark and 360x740
- The sound toggle was a filled teal button in the header, competing with each page's primary action; pressed toggles are now tinted with a teal edge (kiosk A+ / contrast toggles too).
- At peak time five full-height urgent rows pushed the table below the fold; only the newest three urgent flags are pinned, with "Show all N urgent flags".
- 360 px: the header wrapped onto two lines; the theme switch and user name move into the drawer, the offline pill shortens to "Offline", the rule id breaks instead of overflowing and the Open button no longer stretches to the row height.
- **Removed decoration:** the filled background on the sound toggle.

### Review 5: hardening (axe, offline, viewports)
- axe found dark-mode red text at 4.35-4.5:1 on tinted surfaces: dark `red` is now #FF8F85 (5.5:1 or better everywhere; table in 3.3 updated).
- axe found marigold-ink (#0F1E1C in dark) used as text and icon colour off a marigold fill ("vitals needed", "Provisional", warning icon): those now use ink text with a marigold dot, and the icon uses marigold in dark.
- The sound toggle's accessible name did not contain its visible text; it now does.
- The kiosk header overflowed at 360 px and by 16 px at 800 px in Marathi with "Listen again" showing: below 640 px the header actions are icon-only with their names as labels, and the row wraps.
- The forward slide (translateX 48 px) briefly widened the page; the kiosk root clips horizontal overflow.
- Result: zero serious or critical axe findings on the kiosk (every input type, body map, review, doctor choice, slip), staff board, dosage check (blocked and ok with ruler), summary and audit log, in light and dark.

### Review 6: Best UI polish (walked as a Marathi-only patient, a desk clerk at peak, a doctor running the three scenarios)
- Patient: the red-flag card used a siren icon at body size; a patient should be told calmly, so it is a raised hand at tile size ("Please tell the staff now").
- Patient: chip remove buttons were 40 px and the front/back toggle 56 px; the whole chip is now the 64 px remove target and the toggle is 64 px.
- Doctor: after recording an override the new result (and its dose) stayed above the viewport where the form had scrolled it; every run, recompute and override now brings the result header into view.
- Doctor: on a needs-input result, an alternative rule's formulary note quoted "up to a maximum dose of 2550 mg per day"; notes, conflicts and ranges on alternatives now show only for ok results (unit-tested with the real data).
- Doctor: at 1280 px the drug field collapsed to a sliver (a two-column span inside a one-column grid); fixed.
- Summary labels sat on the textarea baseline and drifted below their values; they now align to the top.
- **Removed decoration:** none needed this pass beyond the siren (replaced, not added).

### Review 7: kiosk identity and scan steps (800x1280, 1280x800, 360x740; en, hi, mr; `docs/screens/kiosk-identity/`)
- The first screenshot run photographed the language screen under the name "method": the capture did not wait for the screen it meant to show. `e2e/screens-identity.spec.ts` now waits for a named screen, then fails if the image is smaller than a floor that a blank page cannot reach.
- Portrait method and consent screens left the lower half empty: tiles, icons and consent rows are larger in portrait.
- At 360 px the medicine row broke "Paracetamol" into three lines beside the flag and pencil; the row now wraps so the name has the full width, with the "Please check" flag on its own line.
- axe: a row's `aria-label` did not contain its visible text; removed (the visible content names the button). "1 seconds" became "1 s".
- **Removed decoration:** none added; the step indicator is a thin bar with labels, like the quiz progress bar.
