import { useEffect, useMemo, useState } from "react";
import { NavLink, useLocation, useParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Save, Siren, Trash2 } from "lucide-react";
import { get, patch, post, put, type PatientView, type SummaryOut, type Timeline } from "../api/client";
import { BodyFigure } from "../components/BodyFigure";
import { Button, DangerButton } from "../components/Button";
import { RedFlagRow } from "../components/RedFlagRow";
import { EmptyState, ErrorState, Notice, Pill, Skeleton, TextArea } from "../components/ui";
import { LANG_NAMES, LANGS, type Lang } from "../i18n/i18n";
import { cn } from "../lib/cn";
import { ageSex, useBodyRegions, useDoctors } from "../lib/hooks";
import { ScanUpload } from "../shared/ScanUpload";
import { VitalsForm, VITAL_FIELDS } from "../shared/VitalsForm";
import { DosageCheck, type DosagePreset } from "./DosageCheck";

const SECTIONS = [
  ["summary", "Summary"],
  ["vitals", "Vitals"],
  ["timeline", "Timeline"],
  ["notes", "Notes"],
  ["dosage", "Dosage check"],
  ["record", "Dosing record"],
] as const;

export function usePatient(token: string, lang: Lang = "en") {
  return useQuery({ queryKey: ["patient", token, lang], queryFn: () => get<PatientView>(`/api/patients/${token}?lang=${lang}`) });
}

export function Workspace() {
  const { token = "", section = "summary" } = useParams();
  const loc = useLocation();
  const preset = (loc.state as { preset?: DosagePreset } | null)?.preset;
  const p = usePatient(token);
  const doctors = useDoctors();
  useEffect(() => {
    try {
      sessionStorage.setItem("mk.doctor.last", token);
      window.dispatchEvent(new Event("mk-last-patient"));
    } catch {
      /* ignore */
    }
  }, [token]);
  if (p.isPending)
    return (
      <div className="flex flex-col gap-3" aria-busy>
        <Skeleton className="h-16" />
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-96" />
      </div>
    );
  if (p.isError) return <ErrorState title="Could not open this patient" message={(p.error as Error).message} onRetry={() => p.refetch()} />;
  const pv = p.data;
  const doc = doctors.data?.find((d) => d.id === pv.assignedDoctor);
  const pending = pv.pendingScans.length;
  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h1 className="text-xl font-bold tabular">{pv.token}</h1>
        <p className="text-md">{ageSex(pv.dosingInputs.ageYears as number | null, pv.dosingInputs.sex as string | null)}</p>
        <p className="text-md font-semibold">{String(pv.complaint.label ?? "Complaint not given yet")}{pv.complaint.text ? `: ${String(pv.complaint.text)}` : ""}</p>
        <p className="text-sm text-muted">{doc ? doc.name : "No doctor chosen"}{pv.queueNumber ? `, token no. ${pv.queueNumber}` : ""}{pv.status === "in_progress" ? ", still on the kiosk" : ""}</p>
        {pv.redFlags.length > 0 && <Pill tone="red" icon={Siren}>{pv.redFlags.length} red flag{pv.redFlags.length > 1 ? "s" : ""}</Pill>}
      </header>
      <nav aria-label="Patient sections" className="-mx-1 overflow-x-auto">
        <ul className="flex min-w-max gap-1 border-b border-line px-1">
          {SECTIONS.map(([k, label]) => (
            <li key={k}>
              <NavLink
                to={`/doctor/p/${token}/${k}`}
                end
                className={() =>
                  cn(
                    "-mb-px inline-flex min-h-10 items-center gap-2 border-b-2 px-3 text-base font-semibold",
                    section === k ? "border-teal text-teal" : "border-transparent text-muted hover:text-ink",
                  )
                }
              >
                {label}
                {k === "timeline" && pending > 0 && <span className="rounded-full bg-marigold px-1.5 text-xs text-on-marigold tabular">{pending}</span>}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      {section === "summary" && <SummarySection pv={pv} />}
      {section === "vitals" && <VitalsSection pv={pv} />}
      {section === "timeline" && <TimelineSection token={token} />}
      {section === "notes" && <NotesSection pv={pv} />}
      {section === "dosage" && (
        <section aria-labelledby="dc-h" className="flex flex-col gap-3">
          <h2 id="dc-h" className="text-lg font-semibold">
            Dosage check
          </h2>
          <DosageCheck key={token} token={token} preset={preset} />
        </section>
      )}
      {section === "record" && <RecordSection pv={pv} />}
    </div>
  );
}

// ---------------------------------------------------------------- summary
function SummarySection({ pv }: { pv: PatientView }) {
  const qc = useQueryClient();
  const [lang, setLang] = useState<Lang>("en");
  const s = useQuery({ queryKey: ["summary", pv.token, lang], queryFn: () => get<SummaryOut>(`/api/patients/${pv.token}/summary?lang=${lang}`) });
  const regions = useBodyRegions();
  const [edits, setEdits] = useState<Record<string, string>>({});
  useEffect(() => setEdits({}), [lang, pv.token]);
  const save = useMutation({
    mutationFn: () => patch<SummaryOut>(`/api/patients/${pv.token}/summary`, { lang, values: edits }),
    onSuccess: (out) => {
      qc.setQueryData(["summary", pv.token, lang], out);
      setEdits({});
    },
  });
  const soc = (pv.socrates ?? {}) as Record<string, { regions?: string[] } | undefined>;
  const site = soc.site?.regions ?? [];
  const rad = soc.radiation?.regions ?? [];
  const fills = useMemo(() => Object.fromEntries([...rad.map((r) => [r, "#E8833A"]), ...site.map((r) => [r, "#C8372D"])]), [site, rad]);
  const views = regions.data ? (["front", "back"] as const).filter((v) => regions.data!.regions.some((r) => r.view === v && fills[r.id])) : [];
  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_18rem]">
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-muted">The patient's own answers, rebuilt the same way every time. Your edits are tracked; the answers are never changed.</p>
          <div role="radiogroup" aria-label="Answer language" className="inline-flex rounded-full border border-line bg-surface p-0.5">
            {LANGS.map((l) => (
              <button key={l} type="button" role="radio" aria-checked={lang === l} onClick={() => setLang(l)} className={cn("min-h-8 rounded-full px-3 text-sm font-semibold", lang === l ? "bg-teal text-on-teal" : "text-muted")}>
                {LANG_NAMES[l]}
              </button>
            ))}
          </div>
        </div>
        {pv.redFlags.length > 0 && (
          <div className="flex flex-col gap-2">
            {pv.redFlags.map((f) => (
              <RedFlagRow key={f.ruleId} flag={f} />
            ))}
          </div>
        )}
        {s.isPending ? (
          <Skeleton className="h-96" />
        ) : s.isError ? (
          <ErrorState title="Could not build the summary" message={(s.error as Error).message} onRetry={() => s.refetch()} />
        ) : (
          <>
            <p className="text-sm text-muted">
              Intake took {s.data.durationText}; {s.data.fieldsCaptured} answers captured. AI drafts, the doctor decides. Red flags come from draft rules awaiting a source check.
            </p>
            {s.data.sections
              .filter((sec) => sec.title !== "Red flags")
              .map((sec) => (
                <section key={sec.title} className="rounded-panel border border-line bg-surface" aria-label={sec.title}>
                  <h3 className="border-b border-line px-4 py-2 text-md font-semibold">{sec.title}</h3>
                  <dl className="divide-y divide-line">
                    {sec.fields.map((f) => (
                      <div key={f.key} className="grid gap-1 px-4 py-1.5 sm:grid-cols-[12rem_minmax(0,1fr)] sm:items-start">
                        <dt className="text-sm font-semibold sm:pt-1.5">
                          {f.label}
                          {f.edited && <span className="ml-2 rounded-full bg-marigold px-1.5 text-xs text-on-marigold">edited</span>}
                        </dt>
                        <dd lang={lang}>
                          {f.editable ? (
                            <textarea
                              aria-label={f.label}
                              value={edits[f.key] ?? f.value}
                              onChange={(e) => setEdits((x) => ({ ...x, [f.key]: e.target.value }))}
                              rows={Math.min(4, Math.max(1, Math.ceil(f.value.length / 70)))}
                              className={cn("w-full resize-none rounded-field border px-2 py-1 text-base [field-sizing:content]", f.missing ? "border-red/60 bg-red-tint" : "border-transparent bg-transparent hover:border-line focus:border-line-strong")}
                            />
                          ) : (
                            <p className="text-base">{f.value}</p>
                          )}
                          {f.missing && !f.edited && <p className="text-xs font-semibold text-red">Missing: not captured at intake</p>}
                          {f.edited && f.original && <p className="text-xs text-muted">Original: {f.original}</p>}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </section>
              ))}
            <div className="sticky bottom-3 flex flex-wrap items-center gap-3 rounded-panel border border-line bg-surface/95 px-4 py-3 backdrop-blur">
              <Button variant="primary" icon={Save} disabled={!Object.keys(edits).length} loading={save.isPending} onClick={() => save.mutate()}>
                Save edits
              </Button>
              <span className="text-sm text-muted" aria-live="polite">
                {save.isSuccess && !Object.keys(edits).length ? `Saved. Edited fields: ${s.data.editedFields.join(", ") || "none"}` : `${Object.keys(edits).length} unsaved change(s)`}
              </span>
              {save.isError && <span className="text-sm font-semibold text-red">{(save.error as Error).message}</span>}
            </div>
            <section className="rounded-panel border border-line bg-surface p-4">
              <h3 className="text-md font-semibold">Short paragraph (template, deterministic)</h3>
              <p className="mt-1 text-base">{s.data.paragraph}</p>
            </section>
          </>
        )}
      </div>
      <aside className="flex flex-col gap-3" aria-label="Body diagram">
        <h3 className="text-md font-semibold">Where it hurts</h3>
        {regions.data && views.length > 0 ? (
          <>
            <div className="flex gap-2">
              {views.map((v) => (
                <figure key={v} className="flex-1 rounded-panel border border-line bg-surface p-2">
                  <BodyFigure catalog={regions.data!} view={v} fills={fills} lang={lang} className="w-full" />
                  <figcaption className="text-center text-xs text-muted">{regions.data!.viewLabels[v]?.[lang]}</figcaption>
                </figure>
              ))}
            </div>
            <p className="flex gap-4 text-xs">
              <span className="inline-flex items-center gap-1"><span className="size-3 rounded-sm bg-[#C8372D]" aria-hidden />Site</span>
              <span className="inline-flex items-center gap-1"><span className="size-3 rounded-sm bg-[#E8833A]" aria-hidden />Spreads to</span>
            </p>
          </>
        ) : (
          <p className="text-sm text-muted">No body region was chosen.</p>
        )}
      </aside>
    </div>
  );
}

// ---------------------------------------------------------------- vitals
function VitalsSection({ pv }: { pv: PatientView }) {
  const v = (pv.vitals ?? {}) as Record<string, unknown>;
  const flags = pv.abnormal;
  const di = pv.dosingInputs as Record<string, unknown>;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section className="rounded-panel border border-line bg-surface p-4" aria-label="Measured vitals">
        <h2 className="text-md font-semibold">Measured by staff</h2>
        {!pv.vitals ? (
          <EmptyState title="No vitals recorded yet">Staff enter them at the desk; you can enter them here too.</EmptyState>
        ) : (
          <>
            <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
              {VITAL_FIELDS.map((f) => (
                <div key={f.key}>
                  <dt className="text-xs text-muted">{f.label}</dt>
                  <dd className={cn("text-lg font-semibold tabular", flags[f.key] && "text-red")}>
                    {v[f.key] === null || v[f.key] === undefined ? "-" : `${String(v[f.key])} ${f.suffix}`}
                    {flags[f.key] && <span className="ml-1 text-xs">({flags[f.key]})</span>}
                  </dd>
                </div>
              ))}
              <div>
                <dt className="text-xs text-muted">BMI</dt>
                <dd className="text-lg font-semibold tabular">{pv.bmi ?? "-"}</dd>
              </div>
            </dl>
            {Object.keys(flags).length > 0 && <Notice tone="warn" className="mt-3">Outside the usual adult range (draft thresholds, doctor decides).</Notice>}
            {typeof di.ageYears === "number" && di.ageYears < 12 && <p className="mt-2 text-xs text-muted">Adult ranges are not applied to children.</p>}
            {pv.weightMismatch && <Notice tone="warn" className="mt-3">{pv.weightMismatch}</Notice>}
          </>
        )}
      </section>
      <section className="rounded-panel border border-line bg-surface p-4" aria-label="Enter vitals">
        <h2 className="mb-3 text-md font-semibold">Enter or correct</h2>
        <VitalsForm patient={pv} />
      </section>
    </div>
  );
}

// ---------------------------------------------------------------- timeline
type Item = Record<string, string | number | null | boolean | object | undefined>;
const MED_COLS = ["nameAsWritten", "strength", "frequencyAsWritten", "durationAsWritten", "notes"];
const LAB_COLS = ["test", "value", "unit", "referenceRange", "flag"];

function TimelineSection({ token }: { token: string }) {
  const t = useQuery({ queryKey: ["timeline", token], queryFn: () => get<Timeline>(`/api/patients/${token}/timeline`) });
  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="flex flex-col gap-4">
        {t.isPending ? (
          <Skeleton className="h-48" />
        ) : t.isError ? (
          <ErrorState title="Could not load scans" message={(t.error as Error).message} onRetry={() => t.refetch()} />
        ) : (
          <>
            <h2 className="text-lg font-semibold">Waiting for your confirmation</h2>
            {t.data.pending.length === 0 ? (
              <p className="text-sm text-muted">No scans are waiting. Staff can attach a scan to this token at the desk, or use the panel on the right.</p>
            ) : (
              t.data.pending.map((p, i) => <PendingScan key={String(p.id)} token={token} index={i} scan={p} />)
            )}
            <h2 className="mt-2 text-lg font-semibold">Confirmed old records</h2>
            {t.data.confirmed.length === 0 ? (
              <EmptyState title="No scanned prescriptions or lab reports attached" />
            ) : (
              t.data.confirmed.map((e, i) => {
                const items = (e.items as Item[]) ?? [];
                const cols = e.type === "prescription" ? MED_COLS : LAB_COLS;
                return (
                  <section key={i} className="rounded-panel border border-line bg-surface p-4">
                    <p className="font-semibold">
                      {String(e.date)} {String(e.type).replace("_", " ")} <span className="font-normal text-muted">({items.length} items, {e.editedByDoctor ? "edited by doctor" : "as read"})</span>
                    </p>
                    <ItemsTable items={items} cols={cols} />
                    <p className="mt-2 text-xs text-muted">Confirmed by {String(e.confirmedBy ?? "unknown")}</p>
                  </section>
                );
              })
            )}
          </>
        )}
      </div>
      <aside className="rounded-panel border border-line bg-surface p-4">
        <h2 className="mb-3 text-md font-semibold">Scan an old record</h2>
        <ScanUpload token={token} role="doctor" />
      </aside>
    </div>
  );
}

function ItemsTable({ items, cols, onEdit }: { items: Item[]; cols: string[]; onEdit?: (i: number, c: string, v: string) => void }) {
  if (!items.length) return <p className="text-sm text-muted">No items.</p>;
  return (
    <div className="mt-2 overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-muted">
            {cols.map((c) => (
              <th key={c} className="px-2 py-1 font-semibold">{c}</th>
            ))}
            {onEdit && <th className="px-2 py-1 font-semibold">review</th>}
          </tr>
        </thead>
        <tbody>
          {items.map((it, i) => (
            <tr key={i} className={cn("border-t border-line", it.needsReview ? "bg-marigold-tint" : "")}>
              {cols.map((c) => (
                <td key={c} className="px-2 py-1">
                  {onEdit ? (
                    <input aria-label={`${c} row ${i + 1}`} defaultValue={it[c] === null || it[c] === undefined ? "" : String(it[c])} onChange={(e) => onEdit(i, c, e.target.value)} className="min-h-8 w-full min-w-24 rounded-field border border-line bg-surface px-2" />
                  ) : (
                    String(it[c] ?? "")
                  )}
                </td>
              ))}
              {onEdit && <td className="px-2 py-1 text-xs">{it.needsReview ? `check: ${((it.reviewReasons as string[]) ?? []).join(", ")}` : ""}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PendingScan({ token, index, scan }: { token: string; index: number; scan: Record<string, unknown> }) {
  const qc = useQueryClient();
  const draft = scan.draft as Record<string, unknown>;
  const [docType, setDocType] = useState(String(draft.documentType ?? "prescription"));
  const [date, setDate] = useState(String(draft.documentDate ?? ""));
  const [meds, setMeds] = useState<Item[]>(() => JSON.parse(JSON.stringify(draft.medications ?? [])));
  const [labs, setLabs] = useState<Item[]>(() => JSON.parse(JSON.stringify(draft.labResults ?? [])));
  const [dx, setDx] = useState(((draft.diagnosesAsWritten as string[]) ?? []).join("\n"));
  const done = () => {
    qc.invalidateQueries({ queryKey: ["timeline", token] });
    qc.invalidateQueries({ queryKey: ["patient", token] });
  };
  const confirm = useMutation({
    mutationFn: () => post(`/api/patients/${token}/timeline/${index}/confirm`, {
      documentType: docType, documentDate: date || null, medications: meds, labResults: labs,
      diagnosesAsWritten: dx.split("\n").map((x) => x.trim()).filter(Boolean),
    }),
    onSuccess: done,
  });
  const discard = useMutation({ mutationFn: () => post(`/api/patients/${token}/timeline/${index}/discard`), onSuccess: done });
  const edit = (setter: typeof setMeds) => (i: number, c: string, v: string) => setter((rows) => rows.map((r, n) => (n === i ? { ...r, [c]: v || null } : r)));
  const nReview = [...meds, ...labs].filter((x) => x.needsReview).length;
  return (
    <section className="flex flex-col gap-3 rounded-panel border-2 border-marigold bg-surface p-4" aria-label="Pending scan">
      <p className="text-sm">
        <span className="font-semibold">Uploaded by {String(scan.uploadedBy)}</span> <span className="text-muted">at {String(scan.uploadedAt).slice(11, 16)}. AI draft: the doctor decides.</span>
      </p>
      <div className="grid gap-4 lg:grid-cols-[14rem_minmax(0,1fr)]">
        {scan.imageAvailable ? (
          <img src={`/api/patients/${token}/scans/${String(scan.id)}/image`} alt="Scanned document" className="w-full rounded-field border border-line" />
        ) : (
          <p className="text-xs text-muted">The image was deleted after the review time limit; the draft remains.</p>
        )}
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-3">
            <label className="flex flex-col text-sm font-semibold">
              Document type
              <select value={docType} onChange={(e) => setDocType(e.target.value)} className="min-h-10 rounded-field border border-line-strong bg-surface px-2 font-normal">
                {["prescription", "lab_report", "discharge_summary", "other"].map((d) => (
                  <option key={d}>{d}</option>
                ))}
              </select>
            </label>
            <label className="flex flex-col text-sm font-semibold">
              Date as written
              <input value={date} onChange={(e) => setDate(e.target.value)} className="min-h-10 rounded-field border border-line-strong bg-surface px-2 font-normal" />
            </label>
          </div>
          {nReview > 0 && <Notice tone="warn">{nReview} item(s) need your review (highlighted).</Notice>}
          <p className="text-sm font-semibold">Medicines</p>
          <ItemsTable items={meds} cols={MED_COLS} onEdit={edit(setMeds)} />
          <p className="text-sm font-semibold">Lab results</p>
          <ItemsTable items={labs} cols={LAB_COLS} onEdit={edit(setLabs)} />
          <TextArea label="Diagnoses as written (one per line)" value={dx} onChange={(e) => setDx(e.target.value)} />
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="primary" icon={Check} loading={confirm.isPending} onClick={() => confirm.mutate()}>
          Confirm and attach to patient
        </Button>
        <DangerButton confirmLabel="Discard this scan now" onConfirm={() => discard.mutate()} icon={Trash2}>
          Discard scan
        </DangerButton>
      </div>
      {(confirm.error || discard.error) && <Notice tone="stop">{((confirm.error || discard.error) as Error).message}</Notice>}
    </section>
  );
}

// ---------------------------------------------------------------- notes
function NotesSection({ pv }: { pv: PatientView }) {
  const qc = useQueryClient();
  const [text, setText] = useState(pv.doctorNotes ?? "");
  const save = useMutation({
    mutationFn: () => put<{ doctorNotes: string }>(`/api/patients/${pv.token}/notes`, { notes: text }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["patient", pv.token] }),
  });
  const dirty = text.trim() !== (pv.doctorNotes ?? "");
  return (
    <section className="flex max-w-3xl flex-col gap-3" aria-label="Doctor's notes">
      <TextArea label="Assessment and plan" rows={10} value={text} onChange={(e) => setText(e.target.value)} placeholder="Assessment, investigations, plan, follow-up. Written by the doctor." />
      <div className="flex items-center gap-3">
        <Button variant="primary" icon={Save} disabled={!dirty} loading={save.isPending} onClick={() => save.mutate()}>
          Save notes
        </Button>
        <span className="text-sm text-muted" aria-live="polite">{save.isSuccess && !dirty ? "Notes saved." : dirty ? "Unsaved changes." : ""}</span>
      </div>
      {save.isError && <Notice tone="stop">{(save.error as Error).message}</Notice>}
    </section>
  );
}

// ---------------------------------------------------------------- dosing record
function RecordSection({ pv }: { pv: PatientView }) {
  const hist = Object.entries(pv.visitHistory ?? {}).sort();
  const checks = (pv.dosingChecks ?? []) as Record<string, unknown>[];
  if (!hist.length && !checks.length)
    return <EmptyState title="Nothing in the dosing record yet">Confirmed dosage checks, History check answers and overrides for this visit appear here.</EmptyState>;
  return (
    <div className="flex max-w-4xl flex-col gap-4">
      {hist.length > 0 && (
        <section className="rounded-panel border border-line bg-surface p-4">
          <h2 className="text-md font-semibold">History check (doctor-confirmed{pv.visitHistoryBy ? ` by ${pv.visitHistoryBy}` : ""})</h2>
          <dl className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-3">
            {hist.map(([k, v]) => (
              <div key={k} className="flex justify-between gap-2 border-b border-line py-1">
                <dt className="truncate text-muted" title={k}>{k}</dt>
                <dd className="font-semibold">{v}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}
      {checks.map((c, i) => (
        <section key={i} className="rounded-panel border border-line bg-surface p-4">
          <p className="font-semibold">
            {String(c.drug)} <span className="font-normal text-muted">for {String(c.indication ?? "-")}, rule {String(c.ruleId)}, data {String(c.dataStatus)}</span>
          </p>
          <p className="text-xs text-muted tabular">Confirmed {String(c.at).slice(0, 16).replace("T", " ")} by {String(c.doctorId)}</p>
          {((c.overrideCategories as string[]) ?? []).map((cat, n) => (
            <p key={n} className="mt-1 text-sm">
              <span className="font-bold text-red">Override</span> ({cat.replaceAll("_", " ")}): {((c.overrideReasons as string[]) ?? [])[n]}
            </p>
          ))}
          {((c.acknowledgedItems as string[]) ?? []).length > 0 && <p className="mt-1 text-xs text-muted">Checked by the doctor: {((c.acknowledgedItems as string[]) ?? []).join("; ")}</p>}
        </section>
      ))}
    </div>
  );
}
