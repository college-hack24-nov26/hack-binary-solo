import { render, screen, within } from "@testing-library/react";
import type { Card } from "../api/client";
import samples from "../gallery/samples.json";
import { ResultCard } from "./ResultCard";
import { DoseRuler } from "./DoseRuler";
import { asResult, type DoseResult } from "./types";

type Sample = { result: unknown; card: Card };
const S = samples as unknown as Record<string, Sample>;

// every number-bearing dose field the engine can return; none of them may appear when status is not ok
function doseStrings(r: DoseResult): string[] {
  const nums = [r.dose_mg, r.volume_ml, r.units, r.daily_total_mg, r.daily_max_mg, ...(r.dose_range_mg ?? [])].filter((x): x is number => typeof x === "number");
  return nums.map((n) => `${n} mg`).concat(r.product ? [r.product] : []);
}

describe("ResultCard dose display rules", () => {
  it("renders the dose figure and the ruler for ok", () => {
    const r = asResult(S.ok!.result);
    render(<ResultCard result={r} card={S.ok!.card} />);
    expect(screen.getByTestId("dose-figure")).toHaveTextContent(`${r.dose_mg} mg`);
    expect(screen.getByTestId("dose-ruler")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Dose ready for doctor review" })).toBeInTheDocument();
  });

  for (const key of ["needs_input", "blocked", "refused"]) {
    it(`shows no dose number and no ruler for ${key}`, () => {
      const r = asResult(S[key]!.result);
      expect(r.status).toBe(key);
      // force dose fields to be present: the card must still not render them when status is not ok
      const poisoned: DoseResult = { ...r, dose_mg: 123.5, dose_range_mg: [100, 150], daily_total_mg: 777, daily_max_mg: 999, product: "tablet 123.5 mg", volume_ml: 6.5, units: 2, plan: { start: "321 mg twice daily", max_per_day_mg: 4321 } };
      const { container } = render(<ResultCard result={poisoned} card={S[key]!.card} />);
      expect(screen.queryByTestId("dose-figure")).toBeNull();
      expect(screen.queryByTestId("dose-ruler")).toBeNull();
      for (const s of [...doseStrings(poisoned), "321 mg", "4321"]) expect(container.textContent).not.toContain(s);
      expect(within(screen.getByTestId("steps")).queryByRole("list")).toBeNull();
    });
  }

  it("DoseRuler draws nothing when status is not ok, even with numbers present", () => {
    const r = { ...asResult(S.ok!.result), status: "needs_input" as const };
    const { container } = render(<DoseRuler result={r} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the DEMO bar only when the result carries demo", () => {
    const r = asResult(S.ok!.result);
    const { rerender } = render(<ResultCard result={r} card={S.ok!.card} />);
    expect(screen.getByText("DEMO - UNVERIFIED DATA")).toBeInTheDocument();
    rerender(<ResultCard result={{ ...r, demo: false }} card={S.ok!.card} />);
    expect(screen.queryByText("DEMO - UNVERIFIED DATA")).toBeNull();
  });

  it("shows the red Override recorded line after an override", () => {
    render(<ResultCard result={asResult(S.override!.result)} card={S.override!.card} />);
    expect(screen.getByTestId("override-recorded")).toHaveTextContent("Override recorded");
  });
});
