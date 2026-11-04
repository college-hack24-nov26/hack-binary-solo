// Read-only view of the engine Result dict (dosing/engine.py). The UI only reads these fields; it never computes or rounds them.
export type Status = "ok" | "needs_input" | "blocked" | "refused";

export type Source = { id: string | null; name: string; url?: string | null; section?: string; status?: string };
export type TextItem = { code?: string; text: string; sources?: Source[]; data_status?: string };
export type Block = { code: string; text: string; overridable?: boolean; sources?: Source[] };
export type NeedsInput = { field: string; why: string };
export type Override = { block: string; code: string; reason: string; doctor_id: string; category: string; category_label: string };
export type Alternative = {
  rule_id: string;
  indication: string;
  data_status: string;
  suggested: boolean;
  selected: boolean;
  dose_range_mg?: [number, number] | null;
  interval_h?: number | null;
  doses_per_day?: number | null;
  duration?: string | null;
  text_regimen?: string | null;
  note?: string | null;
  conflict?: string | null;
  sources: Source[];
};
export type Interaction = TextItem & { severity?: string; blocking?: boolean; origins?: { source: string; scan_date: string | null }[] };
export type Plan = { start?: string; step?: string; max_per_day_mg?: number; note?: string } | string | null;

export type DoseResult = {
  status: Status;
  drug: string | null;
  indication: string | null;
  selected_rule_id: string | null;
  suggested_rule_id: string | null;
  alternatives: Alternative[];
  dose_mg: number | null;
  dose_range_mg: [number, number] | null;
  product: string | null;
  volume_ml: number | null;
  units: number | null;
  interval_h: number | null;
  doses_per_day: number | null;
  daily_total_mg: number | null;
  daily_max_mg: number | null;
  binding_cap: string | null;
  duration: string | null;
  plan: Plan;
  text_regimen: string | null;
  calculation_steps: string[];
  warnings: TextItem[];
  label_warnings: TextItem[];
  blocks: Block[];
  needs_input: NeedsInput[];
  refused_reasons: string[];
  interactions: Interaction[];
  overrides: Override[];
  sources: Source[];
  data_status: string;
  final: boolean;
  pending_confirmations: string[];
  acknowledge_items: string[];
  banner: string;
  demo?: boolean;
  demo_banner?: string;
};

export function asResult(r: unknown): DoseResult {
  return r as DoseResult;
}

/** Engine numbers are shown as the engine sent them (JSON 200.0 arrives as 200). No rounding. */
export function show(n: number | null | undefined): string {
  return n === null || n === undefined ? "" : String(n);
}
