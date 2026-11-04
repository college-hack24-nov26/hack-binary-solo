// Hardening: axe (zero serious/critical), offline (no non-localhost request is even attempted, fonts load from this server),
// no horizontal scroll at the four review viewports, and visible error states.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { answerCurrent, loadDemoAndOpen, loginAs, startKiosk, VIEWPORTS } from "./helpers";

async function axe(page: Page, label: string) {
  // measure the settled screen, not a frame of the slide-in or a colour transition
  await page.evaluate(() => Promise.all(document.getAnimations().filter((a) => a.effect?.getTiming().iterations !== Infinity).map((a) => a.finished.catch(() => undefined))));
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const bad = r.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(bad.map((v) => `${label}: ${v.id} (${v.impact}) ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
}

/** Abort and record every request that is not to this server. */
async function guard(page: Page): Promise<string[]> {
  const outside: string[] = [];
  await page.context().route("**/*", (route) => {
    const u = new URL(route.request().url());
    if (["127.0.0.1", "localhost"].includes(u.hostname) || u.protocol === "data:" || u.protocol === "blob:") return route.continue();
    outside.push(route.request().url());
    return route.abort();
  });
  return outside;
}

test.describe("axe", () => {
  test("kiosk screens", async ({ page }) => {
    await page.setViewportSize(VIEWPORTS["800x1280"]);
    await page.goto("/kiosk");
    await axe(page, "kiosk language");
    await startKiosk(page, "mr");
    await axe(page, "kiosk consent");
    const plan: Record<string, string> = { sex: "male", age_years: "54", weight_kg: "72", chief_complaint: "chest_pain" };
    const checked = new Set<string>();
    for (let i = 0; i < 80; i++) {
      if (await page.getByTestId("kiosk-review").isVisible().catch(() => false)) break;
      const q = page.getByTestId("kiosk-question");
      await q.waitFor();
      const type = (await q.getAttribute("data-type")) ?? "";
      const id = (await q.getAttribute("data-node")) ?? "";
      if (!checked.has(type)) {
        checked.add(type);
        await axe(page, `kiosk ${type}`);
      }
      if (id === "cp_site") {
        await page.getByTestId("region-chest_center").click();
        await axe(page, "kiosk body map selected");
        await page.getByTestId("bm-toggle-list").click();
        await axe(page, "kiosk body map list");
        await page.getByTestId("continue").click();
        await expect(q).not.toHaveAttribute("data-node", "cp_site");
        continue;
      }
      await answerCurrent(page, id, plan[id]);
    }
    await axe(page, "kiosk review");
    await page.getByTestId("confirm-all").click();
    await axe(page, "kiosk doctor choice");
    await page.getByTestId("doctor-any").click();
    await expect(page.getByTestId("token-slip")).toBeVisible();
    await axe(page, "kiosk token slip");
  });

  for (const theme of ["light", "dark"]) {
    test(`staff board and doctor screens (${theme})`, async ({ page }) => {
      await page.setViewportSize(VIEWPORTS["1440x900"]);
      await page.goto("/");
      await page.evaluate((t) => localStorage.setItem("mk.theme", t), theme);
      await loginAs(page, "doctor");
      await loadDemoAndOpen(page, "penicillin_allergy");
      await page.getByTestId("run-check").click();
      await expect(page.getByTestId("result-card")).toHaveAttribute("data-status", "blocked");
      await axe(page, "dosage check blocked");
      await page.getByTestId("override-form").getByLabel("Reason category").selectOption({ index: 1 });
      await page.getByTestId("override-form").getByLabel("Written reason (at least 10 characters)").fill("Mild reaction only; ID consult done");
      await page.getByTestId("record-override").click();
      await expect(page.getByTestId("result-card")).toHaveAttribute("data-status", "ok");
      await axe(page, "dosage check ok with ruler");
      await page.goto("/doctor/audit");
      await expect(page.getByTestId("chain-seal")).toBeVisible();
      await axe(page, "audit log");
      await page.goto("/doctor/p/PT-DEMOC2/summary");
      await expect(page.getByRole("heading", { name: "Where it hurts" })).toBeVisible();
      await axe(page, "doctor summary");
      await page.goto("/staff");
      await expect(page.getByRole("heading", { name: "Today's board" })).toBeVisible();
      await axe(page, "staff board");
    });
  }
});

test("offline: no request leaves this computer and the fonts load locally", async ({ page }) => {
  const outside = await guard(page);
  await page.setViewportSize(VIEWPORTS["1280x800"]);
  await startKiosk(page, "hi");
  await page.getByTestId("opt-agree").click();
  await expect(page.getByTestId("kiosk-question")).toHaveAttribute("data-node", "age_years");
  const fonts = await page.evaluate(async () => {
    await document.fonts.ready;
    return {
      deva: document.fonts.check('700 32px "Noto Sans Devanagari"', "मरीज़"),
      latin: document.fonts.check('400 16px "Noto Sans"', "Token"),
      loaded: Array.from(document.fonts as unknown as Iterable<FontFace>).filter((f) => f.status === "loaded").map((f) => f.family),
    };
  });
  expect(fonts.deva && fonts.latin).toBe(true);
  expect(fonts.loaded.join(",")).toContain("Noto Sans Devanagari");
  await loginAs(page, "doctor");
  await loadDemoAndOpen(page, "child_fever");
  await page.getByTestId("run-check").click();
  await expect(page.getByTestId("result-card")).toBeVisible();
  await page.goto("/doctor/audit");
  await expect(page.getByTestId("chain-seal")).toBeVisible();
  await page.goto("/staff");
  await expect(page.getByRole("heading", { name: "Today's board" })).toBeVisible();
  await page.goto("/gallery");
  await expect(page.getByRole("heading", { name: "Component gallery" })).toBeVisible();
  expect(outside).toEqual([]);
});

for (const [vp, size] of Object.entries(VIEWPORTS)) {
  test(`no horizontal page scroll at ${vp}`, async ({ page }) => {
    await page.setViewportSize(size);
    const wide = async (label: string) => {
      const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(over, `${label} overflows by ${over}px`).toBeLessThanOrEqual(0);
    };
    await page.goto("/kiosk");
    await wide("kiosk language");
    await startKiosk(page, "mr");
    await wide("kiosk consent");
    await loginAs(page, "doctor");
    await loadDemoAndOpen(page, "child_fever");
    await page.getByTestId("run-check").click();
    await expect(page.getByTestId("result-card")).toBeVisible();
    await wide("dosage check");
    await page.goto("/doctor/audit");
    await expect(page.getByTestId("chain-seal")).toBeVisible();
    await wide("audit");
    await page.goto("/staff");
    await expect(page.getByRole("heading", { name: "Today's board" })).toBeVisible();
    await wide("staff board");
  });
}

test("scan upload says plainly when the local model server is down", async ({ page }) => {
  await loginAs(page, "staff");
  await page.goto("/staff");
  await page.getByRole("button", { name: "Add synthetic chest-pain patient" }).click();
  await page.getByTestId("redflag-row").first().getByRole("button", { name: "Open", exact: true }).click();
  await expect(page.getByText("Scanning is unavailable right now")).toBeVisible();
  await page.getByTestId("scan-file").setInputFiles({ name: "rx.png", mimeType: "image/png", buffer: Buffer.from("89504e470d0a1a0a", "hex") });
  await page.getByLabel("The patient agreed to this document being scanned").check();
  await page.getByRole("button", { name: "Read and send to doctor" }).click();
  await expect(page.getByText(/local model server \(Ollama\) is not running/).last()).toBeVisible();
});
