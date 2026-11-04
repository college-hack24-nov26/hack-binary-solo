// The 60-second judge path as a video: docs/screens/demo.webm. Run: VIDEO=1 npx playwright test e2e/demo-video.spec.ts
// kiosk question -> body map -> token slip -> staff board alert -> doctor dose result with ruler -> override -> audit chain verified
import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { LOGINS } from "./helpers";

const OUT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "docs", "screens", "demo.webm");

test("judge path video", async ({ browser }) => {
  test.skip(!process.env.VIDEO, "set VIDEO=1");
  test.setTimeout(180_000);
  const size = { width: 1280, height: 800 };
  const ctx = await browser.newContext({ viewport: size, hasTouch: true, recordVideo: { dir: path.dirname(OUT) + "/.video", size } });
  const page = await ctx.newPage();
  const pause = (ms = 900) => page.waitForTimeout(ms);
  const q = page.getByTestId("kiosk-question");
  const tap = async (id: string) => {
    await page.getByTestId(id).click();
    await pause(450);
  };
  const keys = async (s: string) => {
    for (const ch of s) await tap(`key-${ch}`);
    await tap("continue");
  };

  // 1. kiosk in Marathi: big question, tiles, body map
  await page.goto("/kiosk");
  await pause(1200);
  await page.getByRole("button", { name: /मराठी/ }).click();
  await pause(1500);
  await tap("opt-agree");
  await keys("54");
  await tap("opt-male");
  await keys("72");
  const answers: Record<string, string> = { chief_complaint: "chest_pain" };
  for (let i = 0; i < 20; i++) {
    const id = (await q.getAttribute("data-node")) ?? "";
    if (id === "cp_site") break;
    const type = await q.getAttribute("data-type");
    if (type === "multi_choice") {
      await tap("opt-none");
      await tap("continue");
    } else {
      const w = page.getByTestId(`opt-${answers[id] ?? "no"}`);
      await ((await w.count()) ? w : page.locator("[data-testid^=opt-]").first()).click();
      await pause(400);
    }
    await expect(q).not.toHaveAttribute("data-node", id);
  }
  await pause(1000);
  await page.getByTestId("region-chest_center").click();
  await pause(700);
  await page.getByTestId("region-upper_arm_left").click();
  await pause(1200);
  await tap("continue");
  for (let i = 0; i < 40; i++) {
    if (await page.getByTestId("kiosk-review").isVisible().catch(() => false)) break;
    const id = (await q.getAttribute("data-node")) ?? "";
    const type = await q.getAttribute("data-type");
    if (id === "cp_assoc") {
      await page.getByTestId("opt-sweating").click();
      await page.getByTestId("continue").click();
    } else if (type === "multi_choice") {
      const w = page.getByTestId("opt-none");
      await ((await w.count()) ? w : page.locator("[data-testid^=opt-]").first()).click();
      await page.getByTestId("continue").click();
    } else if (type === "scale_0_10") await page.getByTestId("scale-7").click();
    else if (type === "body_map") {
      const n = page.getByTestId("special-none");
      await ((await n.count()) ? n : page.getByTestId("special-tell_doctor")).click();
    }
    else if (type === "free_text") await page.getByTestId("skip").click();
    else {
      const w = page.getByTestId("opt-no");
      await ((await w.count()) ? w : page.locator("[data-testid^=opt-]").first()).click();
    }
    await expect(q.and(page.locator(`[data-node="${id}"]`))).toHaveCount(0);
    await pause(250);
  }
  await pause(800);
  await page.getByTestId("confirm-all").click();
  await pause(900);
  await page.getByTestId("doctor-dr_general").click();
  await expect(page.getByTestId("stamp")).toBeVisible();
  await pause(1500);
  await page.mouse.wheel(0, 500);
  await pause(2200);

  // 2. staff board: the urgent red flag is already there
  await page.goto("/staff");
  await page.getByLabel("Username").fill(LOGINS.doctor[0]);
  await page.getByLabel("Password").fill(LOGINS.doctor[1]);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByTestId("redflag-row").first()).toBeVisible();
  await pause(3000);

  // 3. doctor: penicillin allergy, blocked, override, dose with ruler
  await page.goto("/doctor/demo");
  await pause(800);
  await page.getByTestId("load-penicillin_allergy").click();
  await expect(page.getByRole("heading", { name: "Dosage check" })).toBeVisible();
  await pause(1200);
  await page.getByTestId("run-check").click();
  await expect(page.getByTestId("result-card")).toHaveAttribute("data-status", "blocked");
  await pause(2500);
  const form = page.getByTestId("override-form");
  await form.getByLabel("Reason category").selectOption({ label: "Benefit outweighs risk" });
  await form.getByLabel("Written reason (at least 10 characters)").pressSequentially("Mild reaction only; ID consult done", { delay: 25 });
  await pause(500);
  await page.getByTestId("record-override").click();
  await expect(page.getByTestId("dose-ruler")).toBeVisible();
  await pause(3500);

  // 4. audit chain verified
  await page.goto("/doctor/audit");
  await expect(page.getByTestId("chain-seal")).toHaveAttribute("data-ok", "true");
  await pause(1200);
  await page.getByRole("button", { name: "Show details" }).first().click();
  await pause(3000);

  const video = page.video();
  await ctx.close();
  if (video) {
    fs.copyFileSync(await video.path(), OUT);
    fs.rmSync(path.dirname(OUT) + "/.video", { recursive: true, force: true });
  }
});
