// Screenshot review set (docs/DESIGN.md section 8). Writes docs/screens/<group>/<name>__<viewport>__<lang>[__dark].png.
// Run one group: SCREENS=gallery npx playwright test e2e/screens.spec.ts
import { test, type Page } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { kioskToQuestion, loadDemoAndOpen, loginAs, startKiosk, VIEWPORTS } from "./helpers";

const OUT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "docs", "screens");
const only = (process.env.SCREENS ?? "").split(",").filter(Boolean);
const want = (g: string) => only.length === 0 || only.includes(g);

async function shot(page: Page, group: string, name: string, vp: string, lang: string, dark = false, fullPage = true) {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(350);
  await page.screenshot({ path: path.join(OUT, group, `${name}__${vp}__${lang}${dark ? "__dark" : ""}.png`), fullPage });
}

for (const [vp, size] of Object.entries(VIEWPORTS)) {
  test.describe(`viewport ${vp}`, () => {
    test.use({ viewport: size });

    test(`gallery ${vp}`, async ({ page }) => {
      test.skip(!want("gallery"));
      for (const lang of ["en", "hi", "mr"]) {
        for (const theme of ["light", "dark"]) {
          if (vp === "360x740" && theme === "dark" && lang !== "en") continue;
          await page.goto(`/gallery?lang=${lang}&theme=${theme}`);
          await page.getByRole("heading", { name: "Component gallery" }).waitFor();
          await shot(page, "gallery", "gallery", vp, lang, theme === "dark");
        }
      }
    });

    test(`kiosk ${vp}`, async ({ page }) => {
      test.skip(!want("kiosk") || vp === "1440x900");
      for (const lang of ["en", "hi", "mr"] as const) {
        await page.goto("/kiosk");
        await shot(page, "kiosk", "01-language", vp, lang, false, false);
        await startKiosk(page, lang);
        await shot(page, "kiosk", "02-consent", vp, lang, false, false);
        await kioskToQuestion(page, "cp_onset");
        await shot(page, "kiosk", "03-question-tiles", vp, lang, false, false);
      }
    });

    test(`doctor ${vp}`, async ({ page }) => {
      test.skip(!want("doctor") || vp === "800x1280");
      await loginAs(page, "doctor");
      await loadDemoAndOpen(page, "child_fever");
      for (const theme of ["light", "dark"]) {
        await page.evaluate((t) => localStorage.setItem("mk.theme", t), theme);
        await page.reload();
        await page.getByTestId("result-card").or(page.getByRole("button", { name: "Run dosage check" })).first().waitFor();
        await shot(page, "doctor", "dosage-check", vp, "en", theme === "dark");
      }
    });
  });
}
