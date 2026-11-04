// Staff desk is live: a red flag raised on the kiosk and a help request appear on the open board without a reload.
import { expect, test } from "@playwright/test";
import { answerCurrent, loginAs, startKiosk } from "./helpers";

const RED = { sex: "male", age_years: "54", weight_kg: "72", chief_complaint: "chest_pain", cp_site: "chest_center", cp_assoc: "sweating" };

test("kiosk red flag and help request reach the staff board live", async ({ browser }) => {
  const staffCtx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const staff = await staffCtx.newPage();
  await loginAs(staff, "staff");
  await expect(staff.getByRole("heading", { name: "Today's board" })).toBeVisible();
  let reloads = 0;
  staff.on("framenavigated", (f) => f === staff.mainFrame() && reloads++);
  const before = reloads;

  const kioskCtx = await browser.newContext({ viewport: { width: 800, height: 1280 }, hasTouch: true });
  const kiosk = await kioskCtx.newPage();
  await startKiosk(kiosk, "en");
  let token = "";
  for (let i = 0; i < 40; i++) {
    const q = kiosk.getByTestId("kiosk-question");
    await q.waitFor();
    const id = (await q.getAttribute("data-node")) ?? "";
    if (id === "cp_course") break;                  // the red flag fires on the associated-symptoms answer
    await answerCurrent(kiosk, id, RED[id as keyof typeof RED]);
  }
  token = (await kiosk.evaluate(() => JSON.parse(sessionStorage.getItem("mk.kiosk") ?? "{}").token)) as string;
  expect(token).toMatch(/^PT-/);

  const row = staff.getByTestId("redflag-row").filter({ hasText: token });
  await expect(row).toBeVisible({ timeout: 15_000 });
  await expect(row).toContainText("Urgent");
  await expect(row).toContainText("Draft rule, source check pending");
  await expect(row).toContainText("Sweating");

  await kiosk.getByTestId("help").click();
  await expect(kiosk.getByText("Staff have been told. Someone will come to you.")).toBeVisible();
  const banner = staff.getByTestId("help-banner");
  await expect(banner).toContainText(token, { timeout: 15_000 });
  await banner.getByRole("button", { name: "Dismiss" }).click();
  await expect(banner).toHaveCount(0);
  expect(reloads).toBe(before);

  // the patient panel shows the answers and takes vitals
  await row.getByRole("button", { name: "Open" }).click();
  await staff.getByLabel("BP systolic").fill("80");
  await staff.getByLabel("BP diastolic").fill("90");
  await staff.getByRole("button", { name: "Save vitals" }).click();
  await expect(staff.getByText("Systolic must be higher than diastolic.")).toBeVisible();
  await staff.getByLabel("BP systolic").fill("150");
  await staff.getByRole("button", { name: "Save vitals" }).click();
  await expect(staff.getByText("Vitals saved. The doctor can see them now.")).toBeVisible();
  await expect(staff.getByText(/Dosage check|dose/i)).toHaveCount(0);       // no dosing anywhere on the staff desk
});
