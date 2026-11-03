"""Generate synthetic printed documents (fake names, fake clinic) + expected values.
Run: .venv/bin/python scripts/make_fixtures.py"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "fixtures"
FONTS = ["/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
BOLDS = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def font(size, bold=False):
    for f in (BOLDS if bold else FONTS):
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default(size)


def draw_doc(name, header, lines, footer):
    img = Image.new("RGB", (1240, 1754), "white")
    d = ImageDraw.Draw(img)
    y = 70
    d.text((70, y), header[0], font=font(44, True), fill="black"); y += 62
    for h in header[1:]:
        d.text((70, y), h, font=font(28), fill=(40, 40, 40)); y += 40
    d.line((70, y + 10, 1170, y + 10), fill="black", width=3); y += 40
    for text, bold in lines:
        d.text((70, y), text, font=font(32, bold), fill="black"); y += 52
    d.text((70, 1650), footer, font=font(24), fill=(90, 90, 90))
    img.save(OUT / f"{name}.png")


def main():
    OUT.mkdir(exist_ok=True)
    ft = "SYNTHETIC DEMO DOCUMENT - fake data, not a real patient"
    docs = {
        "rx_01": dict(
            header=["Dr. Test Sharma, MBBS", "Demo Clinic, Faketown", "Date: 12/03/2024"],
            lines=[("Patient: Ramesh Demo   Age/Sex: 45/M", False), ("Dx: Fever with body ache", False), ("Rx", True),
                   ("1. Tab. Paracetamol 500 mg   1-0-1   x 3 days", False),
                   ("2. Tab. Pantoprazole 40 mg   OD   x 5 days", False),
                   ("3. Tab. Cetirizine 10 mg   HS   x 5 days", False)],
            expect={"documentType": "prescription", "meds": [
                ["Paracetamol", "1-0-1"], ["Pantoprazole", "OD"], ["Cetirizine", "HS"]]}),
        "rx_02": dict(
            header=["Dr. Anita Example, MD", "Sample Hospital OPD", "Date: 05/11/2023"],
            lines=[("Patient: Sunita Sample   Age/Sex: 38/F", False), ("Dx: Acute tonsillitis", False), ("Rx", True),
                   ("1. Cap. Amoxicillin 500 mg   TDS   x 5 days", False),
                   ("2. Tab. Ibuprofen 400 mg   SOS", False),
                   ("3. Syp. Cetirizine 5 mg/5 ml   BD   x 3 days", False),
                   ("4. Tab. Metronidazole 400 mg   1-1-1   x 5 days", False)],
            expect={"documentType": "prescription", "meds": [
                ["Amoxicillin", "TDS"], ["Ibuprofen", "SOS"], ["Cetirizine", "BD"], ["Metronidazole", "1-1-1"]]}),
        "rx_03_misspelled": dict(
            header=["Dr. Vikram Mock, MBBS", "Placeholder Clinic", "Date: 20/01/2024"],
            lines=[("Patient: Test Patient   Age/Sex: 60/M", False), ("Dx: Type 2 DM, HTN", False), ("Rx", True),
                   ("1. Tab. Metformin 500 mg   BD   x 30 days", False),
                   ("2. Tab. Amlodipne 5 mg   OD   x 30 days", False),
                   ("3. Tab. Zorbitex 10 mg   OD   x 30 days", False)],
            expect={"documentType": "prescription", "meds": [
                ["Metformin", "BD"], ["Amlodipne", "OD"], ["Zorbitex", "OD"]]},
            # deliberately misspelled / unknown names: must be copied verbatim and flagged
        ),
    }
    for name, c in docs.items():
        draw_doc(name, c["header"], c["lines"], ft)
        (OUT / f"{name}.expected.json").write_text(json.dumps(c["expect"], indent=1))

    labs = [("Test", "Result", "Unit", "Reference"), ("Hemoglobin", "11.2", "g/dL", "13.0 - 17.0"),
            ("Total WBC count", "7800", "/cumm", "4000 - 11000"), ("Platelet count", "2.1", "lakh/cumm", "1.5 - 4.5"),
            ("Fasting blood sugar", "142", "mg/dL", "70 - 100"), ("Serum creatinine", "0.9", "mg/dL", "0.7 - 1.3")]
    img = Image.new("RGB", (1240, 1754), "white")
    d = ImageDraw.Draw(img)
    d.text((70, 70), "DEMO PATHOLOGY LAB", font=font(44, True), fill="black")
    d.text((70, 135), "Report Date: 18/02/2024    Patient: Mohan Fake, 52/M", font=font(28), fill=(40, 40, 40))
    d.line((70, 190, 1170, 190), fill="black", width=3)
    y = 230
    for i, row in enumerate(labs):
        for x, cell in zip((70, 480, 680, 900), row):
            d.text((x, y), cell, font=font(32, i == 0), fill="black")
        y += 62
    d.text((70, 1650), ft, font=font(24), fill=(90, 90, 90))
    img.save(OUT / "lab_01.png")
    (OUT / "lab_01.expected.json").write_text(json.dumps(
        {"documentType": "lab_report", "labs": [[r[0], r[1], r[2]] for r in labs[1:]]}, indent=1))
    print("wrote", sorted(p.name for p in OUT.glob("*.png")))


if __name__ == "__main__":
    sys.exit(main())
