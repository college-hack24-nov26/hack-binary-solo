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

/** From the kiosk language screen to the consent question. */
export async function startKiosk(page: Page, lang: "en" | "hi" | "mr") {
  await page.goto("/kiosk");
  await page.getByRole("button", { name: new RegExp(LANG_LABEL[lang]) }).click();
  await expect(page.getByTestId("kiosk-question")).toBeVisible();
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
