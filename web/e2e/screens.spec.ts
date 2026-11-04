// Screenshot review set (docs/DESIGN.md section 8) written to docs/screens/<surface>/<screen>__<viewport>__<lang>[__dark].jpg.
// Run everything:   npx playwright test e2e/screens.spec.ts
// One surface:      SCREENS=kiosk npx playwright test e2e/screens.spec.ts
import { expect, test, type Page } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadDemoAndOpen, loginAs, startKiosk, VIEWPORTS } from "./helpers";

const OUT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "docs", "screens");
const only = (process.env.SCREENS ?? "").split(",").filter(Boolean);
const want = (g: string) => only.length === 0 || only.includes(g);
type Lang = "en" | "hi" | "mr";

test.setTimeout(240_000);

async function shot(page: Page, group: string, name: string, vp: string, lang: string, dark = false, fullPage = false) {
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => Promise.all(document.getAnimations().filter((a) => a.effect?.getTiming().iterations !== Infinity).map((a) => a.finished.catch(() => undefined))));
  await page.waitForTimeout(150);
  await page.screenshot({ path: path.join(OUT, group, `${name}__${vp}__${lang}${dark ? "__dark" : ""}.jpg`), fullPage, type: "jpeg", quality: 78 });
}

const PLAN: Record<string, string> = { age_years: "54", sex: "male", weight_kg: "72", chief_complaint: "chest_pain" };

/** One full kiosk visit, photographing each screen type once. */
async function kioskVisit(page: Page, vp: string, lang: Lang) {
  const g = "kiosk";
  await page.goto("/kiosk");
  await shot(page, g, "01-language", vp, lang);
  await startKiosk(page, lang);
  await shot(page, g, "02-consent", vp, lang);
  await page.getByTestId("opt-agree").click();
  const seen = new Set<string>();
  const q = page.getByTestId("kiosk-question");
  for (let i = 0; i < 80; i++) {
    if (await page.getByTestId("kiosk-review").isVisible().catch(() => false)) break;
    await q.waitFor();
    const id = (await q.getAttribute("data-node")) ?? "";
    const type = (await q.getAttribute("data-type")) ?? "";
    if (!seen.has(type)) {
      seen.add(type);
      await shot(page, g, `03-${type}`, vp, lang);
    }
    if (id === "cp_site") {
      await page.getByTestId("region-chest_center").click();
      await page.getByTestId("region-upper_arm_left").click();
      await shot(page, g, "04-bodymap-selected", vp, lang);
      await page.getByTestId("bm-toggle-list").click();
      await shot(page, g, "05-bodymap-list", vp, lang);
      await page.getByTestId("continue").click();
    } else if (id === "cp_assoc") {
      await page.getByTestId("opt-sweating").click();
      await page.getByTestId("continue").click();
      await expect(q).not.toHaveAttribute("data-node", id);
      await shot(page, g, "06-redflag-message", vp, lang);
      continue;
    } else if (type === "number") {
      for (const ch of PLAN[id] ?? "30") await page.getByTestId(`key-${ch}`).click();
      await page.getByTestId("continue").click();
    } else if (type === "single_choice" || type === "yes_no_unsure") {
      const w = page.getByTestId(`opt-${PLAN[id] ?? "no"}`);
      await ((await w.count()) ? w : page.locator("[data-testid^=opt-]").first()).click();
    } else if (type === "multi_choice") {
      const w = page.getByTestId("opt-none");
      await ((await w.count()) ? w : page.locator("[data-testid^=opt-]").first()).click();
      await page.getByTestId("continue").click();
    } else if (type === "scale_0_10") await page.getByTestId("scale-6").click();
    else if (type === "free_text") {
      await page.getByRole("textbox").fill("tired");
      await page.getByTestId("continue").click();
    } else if (type === "body_map") {
      const n = page.getByTestId("special-none");
      await ((await n.count()) ? n : page.getByTestId("special-tell_doctor")).click();
    }
    await expect(q.and(page.locator(`[data-node="${id}"]`))).toHaveCount(0);
  }
  await shot(page, g, "07-review", vp, lang);
  await page.getByTestId("confirm-all").click();
  await shot(page, g, "08-doctor", vp, lang);
  await page.getByTestId("doctor-dr_general").click();
  await expect(page.getByTestId("stamp")).toBeVisible();
  await shot(page, g, "09-token-slip", vp, lang, false, true);
}

for (const [vp, size] of Object.entries(VIEWPORTS)) {
  test.describe(`viewport ${vp}`, () => {
    test.use({ viewport: size, hasTouch: vp !== "1440x900" });

    test(`gallery ${vp}`, async ({ page }) => {
      test.skip(!want("gallery"));
      // every language and theme at 1280 px; English light and dark at the other widths (keeps docs/screens small)
      for (const lang of vp === "1280x800" ? ["en", "hi", "mr"] : ["en"]) {
        for (const theme of ["light", "dark"]) {
          await page.goto(`/gallery?lang=${lang}&theme=${theme}`);
          await page.getByRole("heading", { name: "Component gallery" }).waitFor();
          await shot(page, "gallery", "gallery", vp, lang, theme === "dark", true);
        }
      }
    });

    for (const lang of ["en", "hi", "mr"] as Lang[]) {
      test(`kiosk ${vp} ${lang}`, async ({ page }) => {
        test.skip(!want("kiosk") || vp === "1440x900" || (vp === "360x740" && lang === "hi"));
        await kioskVisit(page, vp, lang);
      });
    }

    test(`staff and doctor ${vp}`, async ({ page }) => {
      test.skip(!want("desk") || vp === "800x1280");
      await loginAs(page, "doctor");
      for (const theme of ["light", "dark"]) {
        const dark = theme === "dark";
        await page.evaluate((t) => localStorage.setItem("mk.theme", t), theme);
        await page.goto("/staff");
        const add = page.getByRole("button", { name: "Add synthetic chest-pain patient" });
        if (!dark) await add.click();
        await expect(page.getByTestId("redflag-row").first()).toBeVisible();
        await shot(page, "staff", "board", vp, "en", dark);
        await page.getByTestId("redflag-row").first().getByRole("button", { name: "Open", exact: true }).click();
        await expect(page.getByRole("heading", { name: "Answers" })).toBeVisible();
        await shot(page, "staff", "patient", vp, "en", dark);

        await loadDemoAndOpen(page, "penicillin_allergy");
        await page.getByTestId("run-check").click();
        await expect(page.getByTestId("result-card")).toHaveAttribute("data-status", "blocked");
        await shot(page, "doctor", "dosage-blocked", vp, "en", dark);
        await page.getByTestId("override-form").getByLabel("Reason category").selectOption({ index: 1 });
        await page.getByTestId("override-form").getByLabel("Written reason (at least 10 characters)").fill("Mild reaction only; ID consult done");
        await page.getByTestId("record-override").click();
        await expect(page.getByTestId("result-card")).toHaveAttribute("data-status", "ok");
        await shot(page, "doctor", "dosage-override-ok", vp, "en", dark);

        await loadDemoAndOpen(page, "child_fever");
        const none = page.getByTestId("none-apply");
        await page.getByRole("heading", { name: "History check" }).waitFor();
        if (await none.isVisible()) {
          await none.click();
          await page.getByTestId("save-history").click();
        }
        await page.getByLabel("Weight reported by patient is correct").check();
        await page.getByTestId("run-check").click();
        await expect(page.getByTestId("dose-ruler")).toBeVisible();
        await shot(page, "doctor", "dosage-ok-ruler", vp, "en", dark);

        await loadDemoAndOpen(page, "diabetes_kidney");
        await page.getByTestId("run-check").click();
        await expect(page.getByTestId("result-card")).toHaveAttribute("data-status", "needs_input");
        await shot(page, "doctor", "dosage-needs-input", vp, "en", dark);

        await page.goto("/doctor/p/PT-DEMO22/summary");
        await expect(page.getByRole("heading", { name: "Where it hurts" })).toBeVisible();
        await shot(page, "doctor", "summary", vp, "en", dark);
        await page.goto("/doctor/audit");
        await expect(page.getByTestId("chain-seal")).toBeVisible();
        await shot(page, "doctor", "audit-chain", vp, "en", dark);
        await page.goto("/doctor");
        await expect(page.getByRole("heading", { name: "My queue" })).toBeVisible();
        await shot(page, "doctor", "queue", vp, "en", dark);
      }
    });
  });
}
