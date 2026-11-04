import { useActionState, useEffect, useMemo, useRef, useState } from "react";
import { useFormStatus } from "react-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { Play, RefreshCw, Save, ShieldAlert } from "lucide-react";
import { ApiError, post, type Drugs, type EvaluateIn, type Evaluation, type HistoryItem, type HistoryItems, type MissingItem } from "../api/client";
import { get } from "../api/client";
import { Button } from "../components/Button";
import { Combobox } from "../components/Combobox";
import { Checkbox, ErrorState, Notice, Pill, PrototypeBanner, SelectField, Skeleton, TextArea, TextField } from "../components/ui";
import { Disclosure, ResultCard } from "../dosing/ResultCard";
import { asResult, type DoseResult } from "../dosing/types";
import { cn } from "../lib/cn";

export type DosagePreset = { drug?: string; indication?: string | null; selectedRuleId?: string | null };

const PROV: Record<string, { label: string; tone: "marigold" | "green" | "neutral" | "teal" }> = {
  patient_reported: { label: "patient-reported", tone: "marigold" },
  doctor_entered: { label: "doctor-entered", tone: "green" },
  doctor_confirmed: { label: "doctor-confirmed", tone: "green" },
  derived: { label: "derived", tone: "teal" },
  unknown: { label: "unknown", tone: "neutral" },
};

const NUM_INPUTS: { key: string; label: string; suffix?: string }[] = [
  { key: "weight_kg", label: "Confirm or correct weight", suffix: "kg" },
  { key: "height_cm", label: "Height", suffix: "cm" },
  { key: "scr_mg_dl", label: "Serum creatinine", suffix: "mg/dL" },
  { key: "pregnancy_weeks", label: "Weeks of pregnancy" },
  { key: "child_pugh_score", label: "Child-Pugh score" },
  { key: "doses_per_day", label: "Doses per day (only if the rule asks)" },
  { key: "mg_per_kg_per_day", label: "Intended mg/kg/day (only if the rule asks)" },
];
const CHOICE_INPUTS: { key: string; label: string; options: string[] }[] = [
  { key: "pregnant", label: "Pregnant (overrides the quiz)", options: ["yes", "no", "possible"] },
  { key: "pregnancy_trimester", label: "Trimester", options: ["1", "2", "3"] },
  { key: "child_pugh_class", label: "Child-Pugh class", options: ["A", "B", "C"] },
  { key: "g6pd", label: "G6PD", options: ["normal", "deficient", "unknown"] },
];
const NUMERIC = new Set(["pregnancy_trimester", ...NUM_INPUTS.map((n) => n.key)]);

const numberSchema = z.string().trim().refine((v) => v === "" || (!Number.isNaN(Number(v)) && Number(v) >= 0), "Enter a number.");

function toInputs(raw: Record<string, string>): { values: Record<string, string | number>; errors: Record<string, string> } {
  const values: Record<string, string | number> = {};
  const errors: Record<string, string> = {};
  for (const [k, v] of Object.entries(raw)) {
    if (v === undefined || v.trim() === "") continue;
    if (NUMERIC.has(k)) {
      const p = numberSchema.safeParse(v);
      if (!p.success) errors[k] = p.error.issues[0]?.message ?? "Enter a number.";
      else values[k] = Number(v);
    } else values[k] = v.trim();
  }
  return { values, errors };
}

function Prov({ p }: { p: string }) {
  const x = PROV[p] ?? { label: p, tone: "neutral" as const };
  return <Pill tone={x.tone}>{x.label}</Pill>;
}

export function DosageCheck({ token, preset, onConfirmed }: { token: string; preset?: DosagePreset; onConfirmed?: () => void }) {
  const qc = useQueryClient();
  const drugsQ = useQuery({ queryKey: ["drugs"], queryFn: () => get<Drugs>("/api/dosing/drugs"), staleTime: Infinity, retry: false });
  const [drug, setDrug] = useState<string | null>(preset?.drug ?? null);
  const [indication, setIndication] = useState<string | null>(preset?.indication ?? null);
  const [form, setForm] = useState("");
  const [route, setRoute] = useState("");
  const [visit, setVisit] = useState<string[]>([]);
  const [showAll, setShowAll] = useState(false);
  const [raw, setRaw] = useState<Record<string, string>>({});
  const [confirmWeight, setConfirmWeight] = useState(false);
  const [extras, setExtras] = useState<Record<string, string | number>>({});
  const [selectedRule, setSelectedRule] = useState<string | null>(preset?.selectedRuleId ?? null);
  const [override, setOverride] = useState<{ category: string; reason: string } | null>(null);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [ack, setAck] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  const drugs = drugsQ.data?.drugs ?? [];
  const current = drugs.find((d) => d.id === drug);
  useEffect(() => {
    if (current && (!indication || !current.indications.some((i) => i.key === indication))) setIndication(current.indications[0]?.key ?? null);
  }, [current, indication]);

  const resetResult = () => {
    setEvaluation(null);
    setAck(false);
  };

  const parsed = useMemo(() => toInputs(raw), [raw]);
  const buildRequest = (opts: { override?: { category: string; reason: string } | null; rule?: string | null; extra?: Record<string, string | number> }): EvaluateIn => {
    const ex = { ...(opts.extra ?? extras) };
    const exForm = typeof ex.form === "string" ? ex.form : undefined;
    delete ex.form;
    const ov = opts.override === undefined ? override : opts.override;
    return {
      token, drug: drug!, indication, doctorInputs: { ...parsed.values, ...ex }, confirmed: confirmWeight ? ["weight_kg"] : [], visitDrugs: visit,
      selectedRuleId: opts.rule === undefined ? selectedRule : opts.rule, form: exForm ?? (form || null), route: route || null, showAllRules: showAll,
      overrideReason: ov?.reason ?? null, overrideCategory: ov?.category ?? null,
    };
  };

  // bring the new result's header into view (after a run, a recompute or an override)
  const revealResult = () =>
    window.requestAnimationFrame(() => {
      resultRef.current?.focus({ preventScroll: true });
      resultRef.current?.scrollIntoView({ block: "start", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    });

  const evaluate = useMutation({
    mutationFn: (req: EvaluateIn) => post<Evaluation>("/api/dosing/evaluate", req),
    onSuccess: (ev) => {
      setEvaluation(ev);
      setAck(false);
      setSaved(null);
      qc.invalidateQueries({ queryKey: ["audit"] });
      revealResult();
    },
  });

  const run = () => {
    if (!drug || Object.keys(parsed.errors).length) return;
    setOverride(null);          // a fresh run starts without an override (as in the Streamlit panel)
    evaluate.mutate(buildRequest({ override: null }));
  };
  const recompute = (o: Parameters<typeof buildRequest>[0]) => evaluate.mutate(buildRequest(o));

  // Ctrl/Cmd+Enter runs the check from anywhere in the panel
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        run();
      }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  });

  const confirm = useMutation({
    mutationFn: () => post("/api/dosing/confirm", { token, resultId: evaluation!.resultId, acknowledged: ack }),
    onSuccess: () => {
      setSaved("Dosage check confirmed and saved to the record.");
      setEvaluation(null);
      qc.invalidateQueries({ queryKey: ["patient", token] });
      qc.invalidateQueries({ queryKey: ["audit"] });
      onConfirmed?.();
    },
  });

  const result: DoseResult | null = evaluation ? asResult(evaluation.result) : null;
  const canConfirm = evaluation ? (ack ? evaluation.canConfirmIfAcknowledged : evaluation.canConfirm) : false;

  if (drugsQ.isError)
    return <ErrorState title="Dosing is unavailable" message={(drugsQ.error as Error).message} onRetry={() => drugsQ.refetch()} />;

  return (
    <div className="flex flex-col gap-4">
      <PrototypeBanner extra={drugsQ.data?.allowUnverified ? "UNVERIFIED rules are computed and marked." : undefined} />
      <p className="text-sm text-muted">Decision support only. The doctor makes the final decision. Nothing here is shown to the patient.</p>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div className="flex flex-col gap-4">
          {drugsQ.isPending ? (
            <Skeleton className="h-40" />
          ) : (
            <section className="grid gap-3 rounded-panel border border-line bg-surface p-4 sm:grid-cols-2 xl:grid-cols-1" aria-label="Drug and indication">
              <Combobox
                label="Drug"
                options={drugs.map((d) => ({ value: d.id, label: d.generic }))}
                value={drug}
                placeholder="Type to search, e.g. paracetamol"
                onChange={(v) => {
                  setDrug(v);
                  setIndication(null);
                  setSelectedRule(null);
                  setExtras({});
                  setForm("");
                  resetResult();
                }}
              />
              <SelectField label="Indication" value={indication ?? ""} disabled={!current} onChange={(e) => (setIndication(e.target.value), setSelectedRule(null), resetResult())}>
                {!current && <option value="">Choose a drug first</option>}
                {current?.indications.map((i) => (
                  <option key={i.key} value={i.key} title={i.labels.join(" | ")}>
                    {i.key}
                  </option>
                ))}
              </SelectField>
              <div className="sm:col-span-2 xl:col-span-1">
              <Disclosure summary="Optional: pharmacy form, route, other drugs this visit, every rule">
              <div className="grid gap-3 sm:grid-cols-2">
              <SelectField label="Pharmacy form (optional)" value={form} disabled={!current} onChange={(e) => setForm(e.target.value)} help="Blank: the engine suggests a product.">
                <option value="">Suggest a product</option>
                {current?.forms.map((f) => (
                  <option key={f}>{f}</option>
                ))}
              </SelectField>
              <SelectField label="Route (optional)" value={route} onChange={(e) => setRoute(e.target.value)}>
                <option value="">As the rule says</option>
                <option value="oral">oral</option>
                <option value="parenteral">parenteral</option>
                <option value="rectal">rectal</option>
              </SelectField>
              <fieldset className="sm:col-span-2">
                <legend className="text-sm font-semibold">Other drugs prescribed this visit</legend>
                <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
                  {drugs.filter((d) => d.id !== drug).map((d) => (
                    <Checkbox key={d.id} label={d.generic} checked={visit.includes(d.id)} onChange={(e) => setVisit((v) => (e.target.checked ? [...v, d.id] : v.filter((x) => x !== d.id)))} />
                  ))}
                </div>
              </fieldset>
              <Checkbox className="sm:col-span-2" label="Show every rule for this drug that fits the patient" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />
              </div>
              </Disclosure>
              </div>
            </section>
          )}

          {drug && <HistoryCheck token={token} drug={drug} onSaved={resetResult} />}

          <Disclosure summary="Doctor-entered inputs (never defaulted)">
            <div className="grid gap-3 sm:grid-cols-2">
              {NUM_INPUTS.map((n) => (
                <TextField key={n.key} label={n.label} suffix={n.suffix} inputMode="decimal" value={raw[n.key] ?? ""} error={parsed.errors[n.key]} onChange={(e) => setRaw((r) => ({ ...r, [n.key]: e.target.value }))} />
              ))}
              {CHOICE_INPUTS.map((c) => (
                <SelectField key={c.key} label={c.label} value={raw[c.key] ?? ""} onChange={(e) => setRaw((r) => ({ ...r, [c.key]: e.target.value }))}>
                  <option value="">Not entered</option>
                  {c.options.map((o) => (
                    <option key={o}>{o}</option>
                  ))}
                </SelectField>
              ))}
              <TextField className="sm:col-span-2" label="Current medicines (replaces the quiz list)" value={raw.meds_text ?? ""} onChange={(e) => setRaw((r) => ({ ...r, meds_text: e.target.value }))} />
            </div>
          </Disclosure>

          <section className="flex flex-col gap-3 rounded-panel border border-line bg-surface p-4" aria-label="Run">
            <Checkbox label="Weight reported by patient is correct" checked={confirmWeight} onChange={(e) => setConfirmWeight(e.target.checked)} />
            <Button variant={result ? "secondary" : "primary"} icon={Play} loading={evaluate.isPending} disabled={!drug || !indication} onClick={run} data-testid="run-check">
              {result ? "Run dosage check again" : "Run dosage check"}
            </Button>
            <p className="text-xs text-muted">Shortcut: Ctrl+Enter. Every run is written to the audit log.</p>
            {evaluate.isError && <Notice tone="stop" title="The check did not run">{(evaluate.error as Error).message}</Notice>}
          </section>
        </div>

        <div ref={resultRef} tabIndex={-1} className="flex scroll-mt-20 flex-col gap-4 outline-none" aria-live="polite">
          {saved && <Notice tone="ok" title={saved}>It is listed under Dosing record and in the audit log.</Notice>}
          {!result && !saved && (
            <div className="rounded-panel border border-dashed border-line-strong p-6 text-base text-muted">
              Choose a drug and indication, answer the History check, then run the dosage check. The result appears here.
            </div>
          )}
          {result && evaluation && (
            <ResultCard
              result={result}
              card={evaluation.card}
              slots={{
                missing:
                  result.status === "needs_input" ? (
                    <MissingChecklist
                      items={evaluation.card.missing}
                      result={result}
                      forms={current?.forms ?? []}
                      busy={evaluate.isPending}
                      onSubmit={(got, rule) => {
                        const next = { ...extras, ...got };
                        setExtras(next);
                        if (rule) setSelectedRule(rule);
                        recompute({ extra: next, rule: rule ?? undefined });
                      }}
                    />
                  ) : undefined,
                override:
                  result.status === "blocked" && drugsQ.data ? (
                    <OverrideForm
                      categories={drugsQ.data.overrideCategories}
                      onSubmit={async (o) => {
                        setOverride(o);
                        const ev = await post<Evaluation>("/api/dosing/evaluate", buildRequest({ override: o }));
                        setEvaluation(ev);
                        qc.invalidateQueries({ queryKey: ["audit"] });
                        revealResult();
                      }}
                    />
                  ) : undefined,
                alternatives:
                  result.alternatives.length > 1 ? (
                    <Alternatives
                      result={result}
                      onUse={(rid) => {
                        setSelectedRule(rid);
                        recompute({ rule: rid });
                      }}
                    />
                  ) : undefined,
                confirm: (
                  <section className="flex flex-col gap-3 rounded-panel border border-line bg-surface p-4" aria-label="Confirm">
                    {result.acknowledge_items.length > 0 && (
                      <>
                        <Notice tone="warn" title="Not checked by the engine and still unanswered">
                          <ul className="mt-1 list-disc pl-5">
                            {result.acknowledge_items.map((t) => (
                              <li key={t}>{t}</li>
                            ))}
                          </ul>
                        </Notice>
                        <Checkbox label="I have checked these" checked={ack} onChange={(e) => setAck(e.target.checked)} />
                      </>
                    )}
                    <div className="flex flex-wrap items-center gap-3">
                      <Button variant={canConfirm ? "primary" : "secondary"} icon={Save} disabled={!canConfirm} loading={confirm.isPending} onClick={() => confirm.mutate()} data-testid="confirm-check">
                        Confirm and save to record
                      </Button>
                      {!canConfirm && (
                        <span className="text-sm text-muted">
                          {result.status !== "ok"
                            ? "Only a dose that is ready for review can be confirmed."
                            : !result.final
                              ? `Provisional: confirm ${result.pending_confirmations.join(", ") || "the inputs"} first.`
                              : "Tick “I have checked these” first."}
                        </span>
                      )}
                    </div>
                    {confirm.isError && <Notice tone="stop">{(confirm.error as Error).message}</Notice>}
                  </section>
                ),
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- History check
function HistoryCheck({ token, drug, onSaved }: { token: string; drug: string; onSaved: () => void }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["history-items", token, drug], queryFn: () => post<HistoryItems>("/api/dosing/history-items", { token, drug }) });
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const save = useMutation({
    mutationFn: (a: Record<string, string>) => post(`/api/patients/${token}/history`, { answers: a }),
    onSuccess: () => {
      setAnswers({});
      qc.invalidateQueries({ queryKey: ["history-items", token] });
      qc.invalidateQueries({ queryKey: ["patient", token] });
      onSaved();
    },
  });
  useEffect(() => setAnswers({}), [drug]);
  if (q.isPending) return <Skeleton className="h-32" />;
  if (q.isError) return <ErrorState title="Could not load the History check" message={(q.error as Error).message} onRetry={() => q.refetch()} />;
  const { unknown, items, context, medicines, unparsed } = q.data;
  const known = items.filter((i) => !unknown.some((u) => u.field === i.field));
  const answered = Object.fromEntries(Object.entries(answers).filter(([, v]) => v));
  return (
    <section className="rounded-panel border border-line bg-surface" aria-labelledby="hc-h">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
        <h3 id="hc-h" className="text-md font-semibold">
          History check
        </h3>
        {unknown.length > 0 && (
          <Button size="sm" onClick={() => setAnswers(Object.fromEntries(unknown.map((i) => [i.field, "no"])))} data-testid="none-apply">
            None of these apply
          </Button>
        )}
      </header>
      <div className="flex flex-col gap-3 p-4">
        <p className="text-xs text-muted">Answers are saved as doctor-confirmed for this visit and reused for every drug checked. Unanswered items stay unknown, never “no”.</p>
        {known.length > 0 && (
          <p className="text-sm">
            <span className="font-semibold">Already known: </span>
            {known.map((i, n) => (
              <span key={i.field}>
                {n > 0 && "; "}
                {i.label}: {i.value} <span className="text-muted">({PROV[i.prov]?.label ?? i.prov})</span>
              </span>
            ))}
          </p>
        )}
        {unknown.length === 0 ? (
          <Notice tone="ok">Nothing unknown for this drug.</Notice>
        ) : (
          <>
            <ul className="flex flex-col divide-y divide-line">
              {unknown.map((i: HistoryItem) => (
                <li key={i.field} className="py-2">
                  <fieldset>
                    <legend className="text-sm">
                      <span className="font-semibold">{i.label}</span>
                      {i.required && <span className="ml-2 text-xs font-semibold text-red">required</span>}
                      {i.question.replace(/\?$/, "") !== i.label && <span className="block text-muted">{i.question}</span>}
                    </legend>
                    <div className="mt-1 flex gap-1" role="radiogroup" aria-label={i.label}>
                      {["yes", "no", "unsure"].map((v) => (
                        <button
                          key={v}
                          type="button"
                          role="radio"
                          aria-checked={answers[i.field] === v}
                          onClick={() => setAnswers((a) => ({ ...a, [i.field]: a[i.field] === v ? "" : v }))}
                          className={cn("min-h-8 rounded-full border px-3 text-sm font-semibold", answers[i.field] === v ? "border-teal bg-teal text-on-teal" : "border-line-strong bg-surface hover:bg-tint")}
                        >
                          {v}
                        </button>
                      ))}
                    </div>
                  </fieldset>
                </li>
              ))}
            </ul>
            <div className="flex flex-wrap items-center gap-3">
              <Button icon={Save} loading={save.isPending} disabled={!Object.keys(answered).length} onClick={() => save.mutate(answered)} data-testid="save-history">
                Save history answers
              </Button>
              <span className="text-xs text-muted">{Object.keys(answered).length} of {unknown.length} answered</span>
            </div>
            {save.isError && <Notice tone="stop">{(save.error as Error).message}</Notice>}
          </>
        )}
        <Disclosure summary="Patient context (provenance)">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
            {context.map((c) => (
              <div key={c.name}>
                <dt className="text-xs text-muted">{c.label}</dt>
                <dd className="flex flex-wrap items-center gap-1 text-sm font-semibold tabular">
                  {c.value ?? "unknown"} <Prov p={c.provenance} />
                </dd>
              </div>
            ))}
          </dl>
          {(medicines.length > 0 || unparsed.length > 0) && (
            <div className="mt-3">
              <p className="text-sm font-semibold">Current medicines used for interactions</p>
              <ul className="mt-1 text-sm">
                {medicines.map((m) => (
                  <li key={m.generic + m.raw}>
                    <span className="font-semibold">{m.generic}</span> <span className="text-muted">(as written: {m.raw}; {m.sources.join(" and ")})</span>
                  </li>
                ))}
                {unparsed.map((u) => (
                  <li key={u}>Not recognised, doctor to review: “{u}”</li>
                ))}
              </ul>
            </div>
          )}
        </Disclosure>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- needs_input checklist
function MissingChecklist({ items, result, forms, busy, onSubmit }: { items: MissingItem[]; result: DoseResult; forms: string[]; busy: boolean; onSubmit: (got: Record<string, string | number>, rule: string | null) => void }) {
  const [vals, setVals] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);
  const submit = () => {
    const got: Record<string, string | number> = {};
    let rule: string | null = null;
    for (const it of items) {
      const v = (vals[it.field] ?? "").trim();
      if (!v || it.kind === "elsewhere") continue;
      if (it.kind === "rule") rule = v;
      else if (it.kind === "num") {
        if (Number.isNaN(Number(v))) {
          setErr(`${it.field}: enter a number.`);
          return;
        }
        got[it.key] = Number(v);
      } else got[it.key] = v;
    }
    if (!rule && !Object.keys(got).length) {
      setErr("Nothing filled in yet.");
      return;
    }
    setErr(null);
    onSubmit(got, rule);
  };
  return (
    <section className="rounded-panel border border-teal/40 bg-surface p-4" aria-labelledby="mi-h" data-testid="missing-checklist">
      <h4 id="mi-h" className="text-md font-semibold">
        Fill in the missing items
      </h4>
      <ul className="mt-2 flex flex-col divide-y divide-line">
        {items.map((it) => (
          <li key={it.field} className="grid gap-2 py-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,14rem)] sm:items-start">
            <div>
              <p className="font-mono text-sm font-semibold">{it.field}</p>
              <p className="text-sm text-muted">{it.why}</p>
            </div>
            {it.kind === "elsewhere" ? (
              <p className="text-sm text-muted">{it.hint}</p>
            ) : it.kind === "rule" ? (
              <select aria-label={it.field} data-testid={`fill-${it.field}`} className="min-h-10 rounded-field border border-line-strong bg-surface px-2" value={vals[it.field] ?? ""} onChange={(e) => setVals((v) => ({ ...v, [it.field]: e.target.value }))}>
                <option value="">Choose a rule…</option>
                {result.alternatives.map((a) => (
                  <option key={a.rule_id} value={a.rule_id}>
                    {a.rule_id}: {a.indication.slice(0, 60)} ({a.data_status}){a.suggested ? ", suggested" : ""}
                  </option>
                ))}
              </select>
            ) : it.kind === "tri" || it.kind === "choice" || it.kind === "form" ? (
              <select aria-label={it.field} data-testid={`fill-${it.field}`} className="min-h-10 rounded-field border border-line-strong bg-surface px-2" value={vals[it.field] ?? ""} onChange={(e) => setVals((v) => ({ ...v, [it.field]: e.target.value }))}>
                <option value="">Choose…</option>
                {(it.kind === "form" ? forms : it.options).map((o) => (
                  <option key={o}>{o}</option>
                ))}
              </select>
            ) : (
              <input aria-label={it.field} data-testid={`fill-${it.field}`} inputMode={it.kind === "num" ? "decimal" : "text"} className="min-h-10 rounded-field border border-line-strong bg-surface px-3 tabular" value={vals[it.field] ?? ""} onChange={(e) => setVals((v) => ({ ...v, [it.field]: e.target.value }))} />
            )}
          </li>
        ))}
      </ul>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <Button variant="primary" icon={RefreshCw} loading={busy} onClick={submit} data-testid="recompute">
          Update and recompute
        </Button>
        <p aria-live="polite" className="text-sm font-semibold text-red">
          {err}
        </p>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- override
type OvState = { error?: string; field?: "category" | "reason"; category?: string; reason?: string };

function OverrideSubmit() {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" variant="danger" icon={ShieldAlert} loading={pending} data-testid="record-override">
      Record override and show dose
    </Button>
  );
}

function OverrideForm({ categories, onSubmit }: { categories: Record<string, string>; onSubmit: (o: { category: string; reason: string }) => Promise<void> }) {
  const catRef = useRef<HTMLSelectElement>(null);
  const reasonRef = useRef<HTMLTextAreaElement>(null);
  const schema = z.object({
    category: z.string().refine((c) => c in categories, "Choose a reason category."),
    reason: z.string().trim().min(10, "Write a reason of at least 10 characters."),
  });
  const [state, action] = useActionState<OvState, FormData>(async (_p, fd) => {
    const input = { category: String(fd.get("category") ?? ""), reason: String(fd.get("reason") ?? "") };
    const r = schema.safeParse(input);
    if (!r.success) {
      const i = r.error.issues[0]!;
      return { error: i.message, field: i.path[0] as "category" | "reason", ...input };
    }
    try {
      await onSubmit({ category: r.data.category, reason: r.data.reason });
      return {};
    } catch (e) {
      return { error: e instanceof ApiError ? e.message : "The override was not recorded.", ...input };
    }
  }, {});
  useEffect(() => {
    if (state.field === "category") catRef.current?.focus();
    else if (state.field === "reason") reasonRef.current?.focus();
  }, [state]);
  return (
    <form action={action} noValidate className="flex flex-col gap-3 rounded-panel border border-red/50 bg-surface p-4" aria-labelledby="ov-h" data-testid="override-form">
      <h4 id="ov-h" className="text-md font-semibold">
        Override (doctor only, logged)
      </h4>
      <p className="text-sm text-muted">The dose is shown only after a category and a written reason are recorded. Both go into the audit log.</p>
      <SelectField ref={catRef} label="Reason category" name="category" defaultValue={state.category ?? ""} error={state.field === "category" ? state.error : undefined} key={`c${state.category}`}>
        <option value="">Choose…</option>
        {Object.entries(categories).map(([k, v]) => (
          <option key={k} value={k}>
            {v}
          </option>
        ))}
      </SelectField>
      <TextArea ref={reasonRef} label="Written reason (at least 10 characters)" name="reason" defaultValue={state.reason ?? ""} error={state.field === "reason" ? state.error : undefined} key={`r${state.reason}`} />
      {state.error && !state.field && (
        <p className="text-sm font-semibold text-red" role="alert">
          {state.error}
        </p>
      )}
      <div>
        <OverrideSubmit />
      </div>
    </form>
  );
}

// ---------------------------------------------------------------- alternatives
export function Alternatives({ result, onUse }: { result: DoseResult; onUse: (ruleId: string) => void }) {
  const ok = result.status === "ok";
  return (
    <Disclosure summary={`Alternatives side by side (${result.alternatives.length})`} open={result.status === "needs_input"}>
      <ul className="flex flex-col divide-y divide-line">
        {result.alternatives.map((a) => (
          <li key={a.rule_id} className="flex flex-wrap items-start justify-between gap-3 py-2">
            <div className="min-w-0 flex-1">
              <p className="font-semibold">
                {a.rule_id} {a.suggested && <Pill tone="teal">suggested</Pill>} {a.selected && <Pill tone="green">selected</Pill>}
              </p>
              <p className="text-sm">{a.indication}</p>
              <p className="text-xs text-muted" data-testid="alt-meta">
                {a.data_status}
                {/* rule notes and conflicts are formulary dosing text: shown only once the result is ok (no dose number otherwise) */}
                {ok && a.dose_range_mg ? `; range ${a.dose_range_mg[0]} to ${a.dose_range_mg[1]} mg` : ""}
                {ok && a.note ? `; ${a.note}` : ""}
                {ok && a.conflict ? `; conflict: ${a.conflict}` : ""}
              </p>
            </div>
            {!a.selected && (
              <Button size="sm" onClick={() => onUse(a.rule_id)}>
                Use this rule
              </Button>
            )}
          </li>
        ))}
      </ul>
    </Disclosure>
  );
}
