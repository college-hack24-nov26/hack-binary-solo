// Screenshot review set for kiosk steps 1 and 2: docs/screens/kiosk-identity/<screen>__<viewport>__<lang>.jpg
// Unlike the older sets, every capture first waits for real content (a visible heading, fonts loaded, animations settled) and then
// FAILS if the picture is blank or nearly so, so an empty first screen can no longer slip through as a "successful" capture.
//   npx playwright test e2e/screens-identity.spec.ts
import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { registerKiosk, tapDigits, uniqueMobile } from "./helpers";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(HERE, "..", "..", "docs", "screens", "kiosk-identity");
const FIXTURE = path.resolve(HERE, "..", "..", "fixtures", "rx_01.png");
const SIZES = { "800x1280": { width: 800, height: 1280 }, "1280x800": { width: 1280, height: 800 }, "360x740": { width: 360, height: 740 } } as const;
type Lang = "en" | "hi" | "mr";
const LANG_LABEL = { en: "English", hi: "हिन्दी", mr: "मराठी" } as const;

test.setTimeout(180_000);
fs.mkdirSync(OUT, { recursive: true });

async function shot(page: Page, name: string, vp: string, lang: string, size: { width: number; height: number }, full = false, ready = "") {
  if (ready) await expect(page.getByTestId(ready)).toBeVisible();      // the screen we mean to photograph, not the one being left
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => Promise.all(document.getAnimations().filter((a) => a.effect?.getTiming().iterations !== Infinity).map((a) => a.finished.catch(() => undefined))));
  await expect(page.locator("main button:visible, main h1:visible").first()).toBeVisible();
  expect((await page.locator("body").innerText()).trim().length).toBeGreaterThan(20);
  const file = path.join(OUT, `${name}__${vp}__${lang}.jpg`);
  const buf = await page.screenshot({ path: file, fullPage: full, type: "jpeg", quality: 78 });
  const floor = Math.round(size.width * size.height * 0.012);       // a blank page compresses to a few KB; real screens are far above this
  expect(buf.length, `${name} ${vp} ${lang} looks blank (${buf.length} bytes)`).toBeGreaterThan(floor);
}

for (const [vp, size] of Object.entries(SIZES)) {
  for (const lang of ["en", "hi", "mr"] as Lang[]) {
    test(`identity screens ${vp} ${lang}`, async ({ page }) => {
      test.skip(vp === "360x740" && lang === "hi");
      await page.setViewportSize(size);
      await page.goto("/kiosk");
      await page.getByRole("button", { name: new RegExp(LANG_LABEL[lang]) }).waitFor();
      await shot(page, "00-language", vp, lang, size);
      const num = uniqueMobile();
      await page.getByRole("button", { name: new RegExp(LANG_LABEL[lang]) }).click();
      await shot(page, "01-method", vp, lang, size, false, "id-method");
      await page.getByTestId("id-mobile").click();
      await tapDigits(page, num.slice(0, 7));
      await shot(page, "02-number", vp, lang, size, true, "id-number");
      await tapDigits(page, num.slice(7));
      await page.getByTestId("continue").click();
      await tapDigits(page, "48");
      await shot(page, "03-pin", vp, lang, size, true, "id-pin-new");
      await tapDigits(page, "21");
      await tapDigits(page, "4821");
      await shot(page, "04-consent", vp, lang, size, true, "id-consent");
      await page.getByTestId("consent-agree").click();
      await expect(page.getByTestId("scan-step")).toBeVisible();
      await shot(page, "05-scan-home", vp, lang, size, true, "scan-step");
      await page.getByTestId("scan-file").setInputFiles(FIXTURE);
      await shot(page, "06-scan-preview", vp, lang, size, false, "scan-preview");
      await page.getByTestId("scan-use").click();
      await expect(page.getByTestId("scan-progress")).toBeVisible();
      await expect.poll(async () => Number(await page.getByRole("progressbar").last().getAttribute("aria-valuenow"))).toBeGreaterThan(15);
      await shot(page, "07-scan-reading", vp, lang, size, false, "scan-progress");
      await expect(page.getByTestId("scan-card").last()).toHaveAttribute("data-status", "done", { timeout: 30_000 });
      await shot(page, "08-scan-result", vp, lang, size, true);
      await page.getByTestId("med-row").nth(1).click();
      await shot(page, "09-scan-edit", vp, lang, size, false, "row-editor");
      await page.getByTestId("ed-save").click();
      await page.getByTestId("scan-confirm").click();
      await expect(page.getByTestId("papers-count")).toContainText("1");
      await shot(page, "10-scan-confirmed", vp, lang, size, true);
    });
  }
}

test("welcome back screen", async ({ page }) => {
  await page.setViewportSize(SIZES["800x1280"]);
  const num = uniqueMobile();
  await registerKiosk(page, "en", { digits: num });
  await page.evaluate(() => sessionStorage.clear());
  await page.goto("/kiosk");
  await page.getByRole("button", { name: /English/ }).click();
  await page.getByTestId("id-mobile").click();
  await tapDigits(page, num);
  await page.getByTestId("continue").click();
  await tapDigits(page, "0000");
  await shot(page, "11-pin-wrong", "800x1280", "en", SIZES["800x1280"], false, "id-alert");
  await tapDigits(page, "4821");
  await shot(page, "12-welcome-back", "800x1280", "en", SIZES["800x1280"], false, "id-welcome");
});
