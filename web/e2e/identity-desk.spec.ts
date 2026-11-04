// Staff and doctor sides of patient identity: masked board, lookup, PIN reset, walk-in completion, and the doctor's unverified papers.
import { expect, test, type APIRequestContext } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { axeCheck, loginAs, uniqueMobile } from "./helpers";

test.use({ viewport: { width: 1440, height: 900 } });
const FIXTURE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "fixtures", "rx_01.png");
const H = { "X-Requested-With": "medikiosk" };

async function kioskPatient(api: APIRequestContext, mobile: string, pin = "4821", scan = true) {
  const reg = await (await api.post("/api/kiosk/register", { headers: H, data: { type: "mobile", identifier: mobile, pin, consent: { agreed: true, language: "en" } } })).json();
  const s = await (await api.post("/api/kiosk/sessions", { headers: H, data: { language: "en" } })).json();
  const h = { ...H, "X-Kiosk-Key": s.kioskKey, "X-Kiosk-Identity": reg.identityToken };
  await api.post(`/api/kiosk/sessions/${s.token}/bind`, { headers: h });
  let scanId: string | null = null;
  if (scan) {
    const up = await (await api.post(`/api/kiosk/sessions/${s.token}/scans`, { headers: h, multipart: { image: { name: "p.png", mimeType: "image/png", buffer: fs.readFileSync(FIXTURE) } } })).json();
    scanId = up.id;
    await expect.poll(async () => (await (await api.get(`/api/kiosk/sessions/${s.token}/scans/${up.id}`, { headers: h })).json()).status, { timeout: 30_000 }).toBe("done");
    await api.post(`/api/kiosk/sessions/${s.token}/scans/${up.id}/confirm`, { headers: h });
  }
  return { token: s.token as string, scanId, h, identity: reg.identityToken as string };
}

test("staff board shows the masked number, honest status and papers; lookup and PIN reset work", async ({ page, request }) => {
  const mobile = uniqueMobile();
  const p = await kioskPatient(request, mobile);
  await loginAs(page, "staff");
  await page.goto("/staff");
  const row = page.getByRole("row").filter({ hasText: p.token });
  await expect(row).toBeVisible();
  await expect(row.getByTestId("board-masked")).toHaveText(`+91 ••••• ••${mobile.slice(-3)}`);
  await expect(row).toContainText("New");
  await expect(row).toContainText("Identified, no token yet");
  await expect(row.getByTestId("board-papers")).toHaveText("1");
  await expect(page.locator("body")).not.toContainText(mobile);
  await axeCheck(page, "staff board with identity");

  await page.goto("/staff/people");
  await page.getByTestId("people-search").fill(mobile.slice(-3));
  const person = page.getByTestId("person-row").filter({ hasText: `••${mobile.slice(-3)}` }).first();
  await expect(person).toBeVisible();
  await axeCheck(page, "staff people");
  await person.getByTestId("reset-pin").click();
  const pin = (await person.getByTestId("temp-pin").textContent()) ?? "";
  expect(pin).toMatch(/^\d{4}$/);
  const login = await request.post("/api/kiosk/login", { headers: H, data: { type: "mobile", identifier: mobile, pin } });
  expect(login.status()).toBe(200);
  // searching with the full number finds the patient without showing it
  await page.getByTestId("people-search").fill(mobile);
  await expect(page.getByTestId("person-row").first()).toBeVisible();
  await expect(page.locator("body")).not.toContainText(mobile);
});

test("a patient who chose Ask staff is completed at the desk", async ({ page, request }) => {
  const w = await (await request.post("/api/kiosk/walk-in", { headers: H, data: { language: "en" } })).json();
  const s = await (await request.post("/api/kiosk/sessions", { headers: H, data: { language: "en" } })).json();
  await request.post(`/api/kiosk/sessions/${s.token}/bind`, { headers: { ...H, "X-Kiosk-Key": s.kioskKey, "X-Kiosk-Identity": w.identityToken } });
  await loginAs(page, "staff");
  await page.goto("/staff/people");
  const person = page.getByTestId("person-row").filter({ hasText: "Needs the desk" }).first();
  await expect(person).toBeVisible();
  const mobile = uniqueMobile();
  await person.getByLabel("Number", { exact: true }).fill(mobile);
  await person.getByTestId("walkin-complete").click();
  await expect(person.getByTestId("temp-pin")).toHaveText(/^\d{4}$/);
  await expect(page.getByTestId("person-masked").filter({ hasText: `••${mobile.slice(-3)}` }).first()).toBeVisible();
});

test("doctor sees the papers with the unverified label and only the doctor's action reaches the timeline", async ({ page, request }) => {
  const p = await kioskPatient(request, uniqueMobile());
  await loginAs(page, "doctor");
  await page.goto(`/doctor/p/${p.token}/timeline`);
  const panel = page.getByTestId("patient-papers");
  await expect(panel).toBeVisible();
  await expect(panel).toContainText("Patient-supplied, unverified text");
  await expect(panel.getByTestId("unverified-label").first()).toBeVisible();
  await expect(panel.getByRole("img", { name: /paper the patient scanned/ })).toBeVisible();
  await expect(panel).toContainText("Amoxicillin");
  await expect(page.getByText("No scanned prescriptions or lab reports attached")).toBeVisible();     // nothing is in the record's timeline yet
  await axeCheck(page, "doctor patient papers");
  await panel.getByTestId("use-meds").click();
  await expect(panel.getByTestId("used-by")).toContainText("Used by doctor1");
  await expect(page.getByText("No scanned prescriptions or lab reports attached")).toHaveCount(0);
  await expect(page.getByText("Confirmed by doctor1")).toBeVisible();
});
