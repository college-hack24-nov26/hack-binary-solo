// The three docs/DEMO_SCRIPT.md scenarios through the real UI. Expected statuses and numbers come from
// `scripts/dosing_demo.py` output (2026-11-04), not from memory.
import { expect, test, type Page } from "@playwright/test";
import { loadDemoAndOpen, loginAs } from "./helpers";

test.use({ viewport: { width: 1440, height: 900 } });

async function historyNoneApply(page: Page) {
  const none = page.getByTestId("none-apply");
  if (await none.isVisible()) {
    await none.click();
    await page.getByTestId("save-history").click();
    await expect(page.getByText("Nothing unknown for this drug.")).toBeVisible();
  }
}

test("A: child with fever, paracetamol, dose ready after weight confirmed", async ({ page }) => {
  await loginAs(page, "doctor");
  await loadDemoAndOpen(page, "child_fever");
  await expect(page.getByRole("combobox", { name: "Drug" })).toHaveValue(/^paracetamol/);
  await expect(page.getByLabel("Indication", { exact: true })).toHaveValue("pain/fever");
  await historyNoneApply(page);
  await page.getByLabel("Weight reported by patient is correct").check();
  await page.getByTestId("run-check").click();
  const card = page.getByTestId("result-card");
  await expect(card).toHaveAttribute("data-status", "ok");
  await expect(card.getByRole("heading", { name: "Dose ready for doctor review" })).toBeVisible();
  await expect(page.getByTestId("dose-figure")).toContainText("200 mg");
  await expect(page.getByTestId("dose-figure")).toContainText("4 mL of oral liquid 250 mg/5 mL");
  await expect(page.getByTestId("dose-figure")).toContainText("every 6 h");
  await expect(page.getByTestId("dose-figure")).toContainText("Daily total 800 mg");
  await expect(page.getByTestId("dose-figure")).toContainText("daily maximum 960 mg");
  await expect(page.getByTestId("dose-ruler")).toContainText("Rule range 160 to 240 mg");
  await expect(page.getByText("DEMO - UNVERIFIED DATA")).toBeVisible();
  await expect(page.getByText("Prototype data, not clinically verified")).toBeVisible();
  await page.getByTestId("confirm-check").click();
  await expect(page.getByText("Dosage check confirmed and saved to the record.")).toBeVisible();
});

test("B: diabetes and kidney disease, metformin needs input then ok", async ({ page }) => {
  await loginAs(page, "doctor");
  await loadDemoAndOpen(page, "diabetes_kidney");
  await historyNoneApply(page);
  await page.getByLabel("Weight reported by patient is correct").check();
  await page.getByTestId("run-check").click();
  const card = page.getByTestId("result-card");
  await expect(card).toHaveAttribute("data-status", "needs_input");
  await expect(card.getByRole("heading", { name: "More information needed" })).toBeVisible();
  await expect(card).toContainText("2 items must be filled in before a dose can be shown.");
  await expect(page.getByTestId("dose-figure")).toHaveCount(0);
  await expect(page.getByTestId("dose-ruler")).toHaveCount(0);
  await page.getByTestId("fill-selected_rule_id").selectOption("metformin#0");
  await page.getByTestId("fill-scr_mg_dl").fill("1.0");
  await page.getByTestId("recompute").click();
  await expect(card).toHaveAttribute("data-status", "ok");
  await page.getByTestId("steps").locator("summary").click();
  await expect(page.getByTestId("steps")).toContainText("CKD-EPI 2021 eGFR = 87.24");
  await expect(card).toContainText("Start 500 mg twice daily or 850 mg once daily");
  await expect(card).toContainText("Glycomet");
});

test("C: penicillin allergy, amoxicillin blocked, override needs a real reason", async ({ page }) => {
  await loginAs(page, "doctor");
  await loadDemoAndOpen(page, "penicillin_allergy");
  await expect(page.getByLabel("Indication", { exact: true })).toHaveValue("community-acquired pneumonia");
  await historyNoneApply(page);
  await page.getByTestId("run-check").click();
  const card = page.getByTestId("result-card");
  await expect(card).toHaveAttribute("data-status", "blocked");
  await expect(card.getByRole("heading", { name: "Blocked: safety rule" })).toBeVisible();
  await expect(card).toContainText("Contraindication: Serious penicillin/beta-lactam allergy");
  for (const s of ["S4", "S29", "S30", "S3"]) await expect(card).toContainText(s);
  await expect(page.getByTestId("dose-figure")).toHaveCount(0);
  await page.getByTestId("steps").locator("summary").click();
  await expect(page.getByTestId("steps")).toContainText("Hidden until an override is recorded");

  const form = page.getByTestId("override-form");
  await form.getByLabel("Reason category").selectOption({ label: "Benefit outweighs risk" });
  await form.getByLabel("Written reason (at least 10 characters)").fill("short");
  await page.getByTestId("record-override").click();
  await expect(form).toContainText("Write a reason of at least 10 characters.");
  await expect(card).toHaveAttribute("data-status", "blocked");

  await form.getByLabel("Written reason (at least 10 characters)").fill("Mild reaction only; ID consult done");
  await page.getByTestId("record-override").click();
  await expect(card).toHaveAttribute("data-status", "ok");
  await expect(page.getByTestId("override-recorded").first()).toContainText("Override recorded");
  await expect(page.getByTestId("dose-figure")).toContainText("750 mg");
  await expect(page.getByTestId("dose-figure")).toContainText("3 × capsule 250 mg");
  await expect(page.getByTestId("dose-figure")).toContainText("3 doses a day");
  await expect(page.getByTestId("dose-figure")).toContainText("Daily total 2250 mg");

  await page.getByRole("link", { name: "Audit log" }).click();
  await expect(page.getByTestId("chain-seal")).toHaveAttribute("data-ok", "true");
  await expect(page.getByTestId("chain-seal")).toContainText("Chain verified");
  await expect(page.getByRole("cell", { name: "override" }).first()).toBeVisible();
});
