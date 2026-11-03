import type { DoseResult } from "./types";
import { show } from "./types";

/**
 * Dose ruler, drawn only from engine fields: the rule's dose_range_mg band with the delivered dose_mg marker, and a second bar
 * for daily_total_mg against daily_max_mg with binding_cap named. Renders nothing unless status is "ok" and the numbers exist.
 * Positions are geometry only; every printed number is the engine's own value.
 */
export function DoseRuler({ result }: { result: DoseResult }) {
  if (result.status !== "ok") return null;
  const range = result.dose_range_mg;
  const dose = result.dose_mg;
  const hasDose = dose !== null && dose !== undefined && Array.isArray(range) && range.length === 2;
  const total = result.daily_total_mg;
  const max = result.daily_max_mg;
  const hasDaily = total !== null && total !== undefined && max !== null && max !== undefined && max > 0;
  if (!hasDose && !hasDaily) return null;
  return (
    <figure className="flex flex-col gap-4" aria-label="Dose ruler" data-testid="dose-ruler">
      {hasDose && <PerDose lo={range![0]} hi={range![1]} dose={dose!} />}
      {hasDaily && <Daily total={total!} max={max!} cap={result.binding_cap} />}
    </figure>
  );
}

function pct(v: number, top: number) {
  return `${Math.max(0, Math.min(100, (v / top) * 100))}%`;
}

function PerDose({ lo, hi, dose }: { lo: number; hi: number; dose: number }) {
  const top = Math.max(hi, dose) * 1.25;
  const inBand = dose >= lo && dose <= hi;
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-2 text-sm">
        <span className="font-semibold">Per dose</span>
        <span className="tabular text-muted">
          Rule range {show(lo)} to {show(hi)} mg
        </span>
      </div>
      <div className="relative h-10" role="img" aria-label={`Dose ${show(dose)} mg; rule range ${show(lo)} to ${show(hi)} mg`}>
        <div className="absolute inset-x-0 top-4 h-2 rounded-full bg-tint" />
        <div className="absolute top-3 h-4 rounded-sm border border-teal bg-teal/25" style={{ left: pct(lo, top), width: `calc(${pct(hi, top)} - ${pct(lo, top)})` }} />
        <div className="absolute top-0 flex -translate-x-1/2 flex-col items-center" style={{ left: pct(dose, top) }}>
          <span className={`h-10 w-1 rounded-full ${inBand ? "bg-ink" : "bg-red"}`} />
        </div>
      </div>
      <div className="relative h-5 text-xs text-muted tabular">
        <span className="absolute -translate-x-1/2" style={{ left: pct(lo, top) }}>
          {show(lo)}
        </span>
        <span className="absolute -translate-x-1/2" style={{ left: pct(hi, top) }}>
          {show(hi)}
        </span>
      </div>
      <p className="text-sm">
        <span className="font-semibold tabular">{show(dose)} mg</span> delivered{inBand ? ", inside the rule range" : ", outside the rule range"}
      </p>
    </div>
  );
}

function Daily({ total, max, cap }: { total: number; max: number; cap: string | null }) {
  const top = Math.max(total, max) * 1.1;
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-2 text-sm">
        <span className="font-semibold">Per day</span>
        <span className="tabular text-muted">
          {show(total)} of {show(max)} mg daily maximum
        </span>
      </div>
      <div className="relative h-6" role="img" aria-label={`Daily total ${show(total)} mg of ${show(max)} mg maximum`}>
        <div className="absolute inset-y-1 left-0 rounded-sm bg-tint" style={{ width: pct(max, top) }} />
        <div className="absolute inset-y-1 left-0 rounded-sm bg-teal" style={{ width: pct(total, top) }} />
        <div className="absolute inset-y-0 w-0.5 bg-red" style={{ left: pct(max, top) }} aria-hidden />
      </div>
      <p className="mt-1 text-xs text-muted">{cap ? `Binding cap: ${cap}` : "No cap was binding for this dose."}</p>
    </div>
  );
}
