import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

export const VIEWPORTS = {
  "800x1280": { width: 800, height: 1280 },
  "1280x800": { width: 1280, height: 800 },
  "1440x900": { width: 1440, height: 900 },
  "360x740": { width: 360, height: 740 },
} as const;

// test-only logins created by scripts/e2e_server.py in a temporary folder
export const LOGINS = { staff: ["staff_e2e", "staff-e2e-pass"], doctor: ["doctor1", "doctor-e2e-pass"] } as const;

export async function loginAs(page: Page, role: "staff" | "doctor") {
  await page.goto(`/${role}`);
  const [u, p] = LOGINS[role];
  await page.getByLabel("Username").fill(u);
  await page.getByLabel("Password").fill(p);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
}

const LANG_LABEL = { en: "English", hi: "हिन्दी", mr: "मराठी" } as const;

/** From the kiosk language screen to the quiz's consent question, as an "ask staff" walk-in (no number, no PIN). */
export async function startKiosk(page: Page, lang: "en" | "hi" | "mr") {
  await page.goto("/kiosk");
  await page.getByRole("button", { name: new RegExp(LANG_LABEL[lang]) }).click();
  await page.getByTestId("id-staff").click();
  await page.getByTestId("continue").click();
  await expect(page.getByTestId("kiosk-question")).toBeVisible();
}

/** Digits on the on-screen number pad. */
export async function tapDigits(page: Page, digits: string) {
  for (const d of digits) await page.getByTestId(`key-${d}`).click();
}

/** Language screen to the first quiz question for a NEW patient: number, PIN twice, consent. */
export async function registerKiosk(page: Page, lang: "en" | "hi" | "mr", opts: { kind?: "mobile" | "abha"; digits?: string; pin?: string } = {}) {
  const { kind = "mobile", digits = "9876543210", pin = "4821" } = opts;
  await page.goto("/kiosk");
  await page.getByRole("button", { name: new RegExp(LANG_LABEL[lang]) }).click();
  await page.getByTestId(kind === "mobile" ? "id-mobile" : "id-abha").click();
  await tapDigits(page, digits);
  await page.getByTestId("continue").click();
  await expect(page.getByTestId("id-pin-new")).toBeVisible();
  await tapDigits(page, pin);
  await tapDigits(page, pin);
  await page.getByTestId("consent-agree").click();
}

/** Answer through the API-driven kiosk until `nodeId` is on screen, using the first tile or a default for each type. */
export async function kioskToQuestion(page: Page, nodeId: string, answers: Record<string, string> = {}) {
  for (let i = 0; i < 80; i++) {
    const q = page.getByTestId("kiosk-question");
    await q.waitFor();
    const id = await q.getAttribute("data-node");
    if (id === nodeId) return;
    await answerCurrent(page, id ?? "", answers[id ?? ""]);
  }
  throw new Error(`never reached ${nodeId}`);
}

/** Answer whatever is on screen. `choice` is an option id or a typed value. */
export async function answerCurrent(page: Page, nodeId: string, choice?: string) {
  const q = page.getByTestId("kiosk-question");
  const type = await q.getAttribute("data-type");
  const before = nodeId;
  const pick = async (pref: string) => {
    const want = page.getByTestId(`opt-${pref}`);
    await ((await want.count()) ? want : page.locator("[data-testid^=opt-]").first()).click();
  };
  if (type === "consent") await page.getByTestId("opt-agree").click();
  else if (type === "single_choice" || type === "yes_no_unsure") await pick(choice ?? "no");
  else if (type === "multi_choice") {
    await pick(choice ?? "none");
    await page.getByTestId("continue").click();
  } else if (type === "number") {
    for (const ch of choice ?? "30") await page.getByTestId(`key-${ch}`).click();
    await page.getByTestId("continue").click();
  } else if (type === "scale_0_10") await page.getByTestId(`scale-${choice ?? "3"}`).click();
  else if (type === "free_text") {
    await page.getByRole("textbox").fill(choice ?? "Feeling tired");
    await page.getByTestId("continue").click();
  } else if (type === "body_map") {
    if (choice) {
      await page.getByTestId(`region-${choice}`).first().click();
      await page.getByTestId("continue").click();
    } else {
      const none = page.getByTestId("special-none");
      await ((await none.count()) ? none : page.getByTestId("special-tell_doctor")).click();
    }
  }
  await expect(page.getByTestId("kiosk-question").and(page.locator(`[data-node="${before}"]`))).toHaveCount(0);
}

/** Doctor: load a demo fixture from the sidebar and open its Dosage check. */
export async function loadDemoAndOpen(page: Page, key: string) {
  await page.goto("/doctor/demo");
  await page.getByTestId(`load-${key}`).click();
  await expect(page.getByRole("heading", { name: "Dosage check" })).toBeVisible();
}

/** A unique valid mobile number per call so the per-number rate limit and "already registered" never interfere. */
export function uniqueMobile(): string {
  return "9" + String(Math.floor(Math.random() * 1e9)).padStart(9, "0");
}

/** Answer the quiz until the review screen (or `stopAt`), using the first/neutral tile unless `answers` says otherwise. */
export async function answerAll(page: Page, answers: Record<string, string>, stopAt?: string) {
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

/** 1x1 PNGs: a flat grey page reads as "blurry" and a black one as "dark" to the server's quick quality check. */
export const PNG_GREY = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGD4DwABBAEAHz9PZwAAAABJRU5ErkJggg==", "base64");

/** Zero serious or critical axe findings on the settled screen. */
export async function axeCheck(page: Page, label: string) {
  await page.evaluate(() => Promise.all(document.getAnimations().filter((a) => a.effect?.getTiming().iterations !== Infinity).map((a) => a.finished.catch(() => undefined))));
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const bad = r.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(bad.map((v) => `${label}: ${v.id} (${v.impact}) ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
}
