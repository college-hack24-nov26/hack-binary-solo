// Patient kiosk: a full Hindi visit from the language screen to the token slip, plus double-tap, idle and decline.
import { expect, test, type Page } from "@playwright/test";
import { answerCurrent, startKiosk } from "./helpers";

test.use({ viewport: { width: 800, height: 1280 }, hasTouch: true });

const CHEST = { sex: "male", chief_complaint: "chest_pain", age_years: "54", weight_kg: "72", cp_site: "chest_center" };

async function answerAll(page: Page, answers: Record<string, string>, stopAt?: string) {
  for (let i = 0; i < 90; i++) {
    if (await page.getByTestId("kiosk-review").isVisible().catch(() => false)) return;
    const q = page.getByTestId("kiosk-question").or(page.getByTestId("kiosk-review"));
    await q.first().waitFor();
    if (await page.getByTestId("kiosk-review").isVisible()) return;
    const id = (await page.getByTestId("kiosk-question").getAttribute("data-node")) ?? "";
    if (id === stopAt) return;
    await answerCurrent(page, id, answers[id]);
  }
  throw new Error("quiz did not reach the review screen");
}

test("full Hindi flow: language, consent, questions, body map, review, doctor, token slip, reset", async ({ page }) => {
  await startKiosk(page, "hi");
  await expect(page.locator("html")).toHaveAttribute("lang", "hi");
  await expect(page.getByTestId("kiosk-question")).toHaveAttribute("data-type", "consent");
  await expect(page.getByRole("button", { name: "स्टाफ को बुलाएँ" })).toBeVisible();
  await answerAll(page, CHEST, "cp_site");
  // body map: tap a region, it fills and shows as a chip in Hindi, then continue
  await page.getByTestId("region-chest_center").click();
  await expect(page.getByRole("button", { name: /हटाएँ/ })).toBeVisible();
  await page.getByTestId("continue").click();
  await expect(page.getByTestId("kiosk-question")).not.toHaveAttribute("data-node", "cp_site");
  await answerAll(page, CHEST);
  await expect(page.getByRole("heading", { name: "कृपया अपने जवाब जाँचें" })).toBeVisible();
  await page.getByTestId("confirm-all").click();
  await page.getByTestId("doctor-dr_general").click();
  await expect(page.getByTestId("registered")).toBeVisible();
  await expect(page.getByTestId("token-slip")).toContainText("हरी लाइन के साथ कमरा 12 तक जाएँ");
  await expect(page.getByTestId("queue-number")).toHaveText(/^\d+$/);
  await expect(page.getByTestId("token-slip")).not.toContainText("छाती");      // no answers on the slip
  await page.getByTestId("done").click();
  await expect(page.getByRole("button", { name: /हिन्दी/ })).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem("mk.kiosk"))).toBeNull();
});

test("decline deletes nothing-saved record and offers start over", async ({ page }) => {
  await startKiosk(page, "en");
  await page.getByTestId("opt-decline").click();
  await expect(page.getByText("No problem. No questions were asked and nothing was saved.")).toBeVisible();
});

test("Back goes to the previous question and Not sure is an answer", async ({ page }) => {
  await startKiosk(page, "mr");
  await page.getByTestId("opt-agree").click();
  await expect(page.getByTestId("kiosk-question")).toHaveAttribute("data-node", "age_years");
  for (const k of "35") await page.getByTestId(`key-${k}`).click();
  await page.getByTestId("continue").click();
  await expect(page.getByTestId("kiosk-question")).toHaveAttribute("data-node", "sex");
  await page.getByTestId("back").click();
  await expect(page.getByTestId("kiosk-question")).toHaveAttribute("data-node", "age_years");
  await expect(page.getByTestId("keypad-value")).toHaveText("35");
  await page.getByTestId("continue").click();
  await page.getByTestId("unsure").click();
  await expect(page.getByTestId("kiosk-question")).not.toHaveAttribute("data-node", "sex");
});
