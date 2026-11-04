// Kiosk steps 1 and 2: identify (number, PIN, consent), scan papers, then the existing quiz and the token slip.
// New patient at three viewports in en, hi and mr; returning patient; wrong PIN and lockout; declined consent; skipped scan; idle reset; axe.
import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { answerAll, axeCheck, PNG_GREY, registerKiosk, tapDigits, uniqueMobile } from "./helpers";

const FIXTURE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "fixtures", "rx_01.png");
const LANG_LABEL = { en: "English", hi: "हिन्दी", mr: "मराठी" } as const;
const SIZES = { "800x1280": { width: 800, height: 1280 }, "1280x800": { width: 1280, height: 800 }, "360x740": { width: 360, height: 740 } } as const;
test.use({ hasTouch: true });
const CHEST = { sex: "male", chief_complaint: "chest_pain", age_years: "54", weight_kg: "72", cp_site: "chest_center" };

test.beforeAll(() => {
  if (!fs.existsSync(FIXTURE)) throw new Error("fixtures/rx_01.png is missing: run .venv/bin/python scripts/make_fixtures.py");
});

for (const [vp, size] of Object.entries(SIZES)) {
  for (const lang of ["en", "hi", "mr"] as const) {
    test(`new patient: identify, consent, scan, confirm, quiz, token slip (${vp} ${lang})`, async ({ page }) => {
      test.setTimeout(150_000);
      await page.setViewportSize(size);
      await registerKiosk(page, lang, { digits: uniqueMobile() });
      await expect(page.getByTestId("step-indicator")).toHaveAttribute("data-step", "2");
      await expect(page.getByTestId("scan-step")).toBeVisible();
      await page.getByTestId("scan-file").setInputFiles(FIXTURE);
      await page.getByTestId("scan-use").click();
      // real progress, not a spinner at 0%: the stage text and a non-zero percentage appear before the card is done
      const card = page.getByTestId("scan-card").last();
      await expect(page.getByTestId("scan-progress")).toBeVisible();
      await expect.poll(async () => Number(await page.getByRole("progressbar").last().getAttribute("aria-valuenow")), { timeout: 20_000 }).toBeGreaterThan(5);
      await expect(card).toHaveAttribute("data-status", "done", { timeout: 30_000 });
      await expect(page.getByTestId("scan-type")).toBeVisible();
      await expect(page.getByTestId("scan-date")).toContainText("03/09/2026");
      await expect(card.getByTestId("check-flag").first()).toBeVisible();
      await card.getByTestId("med-row").nth(1).click();
      await page.getByTestId("row-editor").getByRole("textbox").nth(1).fill("650 mg");
      await page.getByTestId("ed-save").click();
      await expect(card.getByTestId("check-flag")).toHaveCount(0);
      await card.getByTestId("scan-confirm").click();
      await expect(page.getByTestId("papers-count")).toContainText("1");
      await page.getByTestId("scan-next").click();
      await expect(page.getByTestId("step-indicator")).toHaveAttribute("data-step", "3");
      await answerAll(page, CHEST, "cp_site");
      await page.getByTestId("region-chest_center").click();
      await page.getByTestId("continue").click();
      await expect(page.getByTestId("kiosk-question")).not.toHaveAttribute("data-node", "cp_site");
      await answerAll(page, CHEST);
      await page.getByTestId("confirm-all").click();
      await page.getByTestId("doctor-dr_general").click();
      await expect(page.getByTestId("token-slip")).toBeVisible();
      await expect(page.getByTestId("slip-papers")).toContainText("1");
      await expect(page.getByTestId("slip-id")).toContainText("••");
      await expect(page.getByTestId("token-slip")).not.toContainText(/\d{10}/);          // never the full number
      await page.getByTestId("done").click();
      await expect(page.getByRole("button", { name: new RegExp(LANG_LABEL[lang]) })).toBeVisible();
      expect(await page.evaluate(() => sessionStorage.getItem("mk.kiosk"))).toBeNull();
    });
  }
}

test("returning patient is recognised by number and PIN", async ({ page }) => {
  const num = uniqueMobile();
  await page.setViewportSize(SIZES["800x1280"]);
  await registerKiosk(page, "en", { digits: num });
  await page.getByTestId("scan-skip").click();
  await expect(page.getByTestId("kiosk-question")).toBeVisible();
  // a second tablet visit: same number, now it asks for the PIN, not a new one
  await page.evaluate(() => sessionStorage.clear());
  await page.goto("/kiosk");
  await page.getByRole("button", { name: /English/ }).click();
  await page.getByTestId("id-mobile").click();
  await tapDigits(page, num);
  await page.getByTestId("continue").click();
  await expect(page.getByTestId("id-pin-login")).toBeVisible();
  await tapDigits(page, "4821");
  await expect(page.getByTestId("id-welcome")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  await expect(page.getByTestId("id-welcome")).toContainText(`${num.slice(-3)}`);
  await expect(page.getByTestId("id-welcome")).not.toContainText(num);
  await page.getByTestId("continue").click();
  await expect(page.getByTestId("scan-step")).toBeVisible();
});

test("wrong PIN shows tries left, the fifth wrong PIN locks, and the right PIN is refused while locked", async ({ page }) => {
  const num = uniqueMobile();
  await page.setViewportSize(SIZES["800x1280"]);
  await registerKiosk(page, "en", { digits: num });
  await page.evaluate(() => sessionStorage.clear());
  await page.goto("/kiosk");
  await page.getByRole("button", { name: /English/ }).click();
  await page.getByTestId("id-mobile").click();
  await tapDigits(page, num);
  await page.getByTestId("continue").click();
  for (const left of [4, 3, 2, 1]) {
    await tapDigits(page, "0000");
    await expect(page.getByTestId("id-alert")).toContainText(`${left} tries left`);
  }
  await tapDigits(page, "0000");
  await expect(page.getByTestId("id-alert")).toContainText("ask staff");
  await tapDigits(page, "4821");
  await expect(page.getByTestId("id-alert")).toContainText("ask staff");
  await expect(page.getByTestId("id-welcome")).toHaveCount(0);
});

test("saying no to saving continues as an anonymous walk-in with no scan step", async ({ page }) => {
  await page.setViewportSize(SIZES["800x1280"]);
  await page.goto("/kiosk");
  await page.getByRole("button", { name: /English/ }).click();
  await page.getByTestId("id-abha").click();
  await tapDigits(page, "91123456789012");
  await expect(page.getByTestId("id-feedback")).toHaveAttribute("data-state", "ok");
  await page.getByTestId("continue").click();
  await tapDigits(page, "1357");
  await tapDigits(page, "1357");
  await page.getByTestId("consent-no").click();
  await expect(page.getByTestId("kiosk-question")).toHaveAttribute("data-type", "consent");
  await expect(page.getByTestId("step-indicator")).toHaveAttribute("data-step", "3");
});

test("number pad gives live format feedback", async ({ page }) => {
  await page.goto("/kiosk");
  await page.getByRole("button", { name: /English/ }).click();
  await page.getByTestId("id-mobile").click();
  await expect(page.getByTestId("continue")).toBeDisabled();
  await tapDigits(page, "5");
  await expect(page.getByTestId("id-digits")).toHaveAttribute("data-value", "");           // a mobile number cannot start with 5
  await tapDigits(page, "98765");
  await expect(page.getByTestId("id-feedback")).toContainText("5 more digits");
  await page.getByTestId("key-del").click();
  await expect(page.getByTestId("id-digits")).toHaveAttribute("data-value", "9876");
  await page.getByTestId("id-back").click();
  await page.getByTestId("id-abha").click();
  await expect(page.getByText("We only save this number")).toBeVisible();
});

test("blurry or dark pictures ask for a retake and camera-less devices fall back to upload", async ({ page }) => {
  await page.setViewportSize(SIZES["800x1280"]);
  await registerKiosk(page, "en", { digits: uniqueMobile() });
  await page.getByTestId("scan-take").click();                       // headless Chromium has no camera: the plain fallback appears
  await expect(page.getByText("The camera is not allowed here")).toBeVisible();
  await expect(page.getByTestId("scan-take")).toHaveCount(0);
  await page.getByTestId("scan-file").setInputFiles({ name: "grey.png", mimeType: "image/png", buffer: PNG_GREY });
  await page.getByTestId("scan-use").click();
  await expect(page.getByTestId("scan-notice")).toBeVisible();
  await expect(page.getByTestId("scan-card")).toHaveCount(0);
});

test("skipping the scan step goes straight to the problem questions", async ({ page }) => {
  await page.setViewportSize(SIZES["1280x800"]);
  await registerKiosk(page, "en", { digits: uniqueMobile() });
  await page.getByTestId("scan-skip").click();
  await expect(page.getByTestId("step-indicator")).toHaveAttribute("data-step", "3");
  await expect(page.getByTestId("kiosk-question")).toBeVisible();
});

test("idle: a visible countdown over the last 10 s, then the tablet starts over and clears the session", async ({ page }) => {
  await page.clock.install();
  await page.setViewportSize(SIZES["800x1280"]);
  await page.goto("/kiosk");
  await page.getByRole("button", { name: /English/ }).click();
  await page.getByTestId("id-mobile").click();
  await tapDigits(page, "98765");
  await page.clock.runFor(45_000);
  await expect(page.getByRole("alertdialog")).toHaveCount(0);
  await page.clock.runFor(8_000);
  await expect(page.getByRole("alertdialog")).toContainText("Are you still there?");
  await expect(page.getByRole("alertdialog")).toContainText(/\b[1-9]0?\b seconds/);
  await page.clock.runFor(12_000);
  await expect(page.getByRole("button", { name: /English/ })).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem("mk.kiosk"))).toBeNull();
});

test("axe: every new kiosk screen", async ({ page }) => {
  test.setTimeout(120_000);
  await page.setViewportSize(SIZES["800x1280"]);
  await page.goto("/kiosk");
  await page.getByRole("button", { name: /मराठी/ }).click();
  await axeCheck(page, "identify method");
  await page.getByTestId("id-abha").click();
  await tapDigits(page, "911234");
  await axeCheck(page, "identify number (partial)");
  await page.getByTestId("id-back").click();
  await page.getByTestId("id-mobile").click();
  await tapDigits(page, uniqueMobile());
  await page.getByTestId("continue").click();
  await axeCheck(page, "pin choose");
  await tapDigits(page, "4821");
  await axeCheck(page, "pin again");
  await tapDigits(page, "4821");
  await axeCheck(page, "consent");
  await page.getByTestId("consent-agree").click();
  await expect(page.getByTestId("scan-step")).toBeVisible();
  await axeCheck(page, "scan home");
  await page.getByTestId("scan-file").setInputFiles(FIXTURE);
  await axeCheck(page, "scan preview");
  await page.getByTestId("scan-use").click();
  await expect(page.getByTestId("scan-progress")).toBeVisible();
  await axeCheck(page, "scan reading");
  await expect(page.getByTestId("scan-card").last()).toHaveAttribute("data-status", "done", { timeout: 30_000 });
  await axeCheck(page, "scan result with flagged row");
  await page.getByTestId("med-row").nth(1).click();
  await axeCheck(page, "row editor");
  await page.getByTestId("ed-save").click();
  await page.getByTestId("scan-confirm").click();
  await axeCheck(page, "scan confirmed");
});
