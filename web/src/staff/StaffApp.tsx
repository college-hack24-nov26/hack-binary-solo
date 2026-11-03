import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Route, Routes, useNavigate, useParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, ClipboardList, FileScan, FlaskConical, LayoutList, Search, UserRound, Volume2, VolumeX, X } from "lucide-react";
import { get, post, put, qs, type Board, type BoardRow, type HelpRequest, type Me, type PatientView } from "../api/client";
import { Button, ToggleButton } from "../components/Button";
import { DataTable, type Column } from "../components/DataTable";
import { RedFlagRow } from "../components/RedFlagRow";
import { EmptyState, ErrorState, Notice, Pill, SelectField, Skeleton } from "../components/ui";
import { LANG_NAMES, LANGS, type Lang } from "../i18n/i18n";
import { cn } from "../lib/cn";
import { ageSex, useConfig, useDebounced, useDoctors, useLiveEvents, type LiveEvent } from "../lib/hooks";
import { RequireRole } from "../shell/auth";
import { DashboardShell, type NavItem } from "../shell/DashboardShell";
import { ShortcutsOverlay } from "../shell/Shortcuts";
import { ScanUpload } from "../shared/ScanUpload";
import { VitalsForm } from "../shared/VitalsForm";

// ---------------------------------------------------------------- alert sound (generated locally, no file, mutable)
function useChime(): [boolean, (v: boolean) => void, () => void] {
  const [on, setOn] = useState(() => {
    try {
      return localStorage.getItem("mk.staff.sound") !== "0";
    } catch {
      return true;
    }
  });
  const ctx = useRef<AudioContext | null>(null);
  const set = (v: boolean) => {
    setOn(v);
    try {
      localStorage.setItem("mk.staff.sound", v ? "1" : "0");
    } catch {
      /* ignore */
    }
  };
  const play = useCallback(() => {
    if (!on) return;
    try {
      ctx.current ??= new AudioContext();
      const c = ctx.current;
      const t0 = c.currentTime;
      for (const [i, f] of [660, 880].entries()) {
        const o = c.createOscillator();
        const g = c.createGain();
        o.frequency.value = f;
        g.gain.setValueAtTime(0.0001, t0 + i * 0.18);
        g.gain.exponentialRampToValueAtTime(0.12, t0 + i * 0.18 + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, t0 + i * 0.18 + 0.25);
        o.connect(g).connect(c.destination);
        o.start(t0 + i * 0.18);
        o.stop(t0 + i * 0.18 + 0.3);
      }
    } catch {
      /* audio not allowed before a click: silent */
    }
  }, [on]);
  return [on, set, play];
}

function useHelp() {
  return useQuery({ queryKey: ["help"], queryFn: () => get<{ items: HelpRequest[] }>("/api/staff/help-requests"), refetchInterval: 15_000 });
}

function Staff() {
  const nav = useNavigate();
  const cfg = useConfig();
  const help = useHelp();
  const [sound, setSound, chime] = useChime();
  const onEvent = useCallback((e: LiveEvent) => {
    if ((e.type === "redflag.triggered" && e.data.severity === "urgent") || (e.type === "help.requested" && !e.data.dismissed)) chime();
  }, [chime]);
  useLiveEvents(onEvent);
  const n = help.data?.items.length ?? 0;
  const items: NavItem[] = [
    { to: "/staff", label: "Board", icon: LayoutList, end: true },
    { to: "/staff/patient", label: "Patient", icon: UserRound },
    { to: "/staff/scans", label: "Scans", icon: FileScan },
    { to: "/staff/help", label: "Help requests", icon: BellRing, count: n },
  ];
  return (
    <RequireRole roles={["staff", "doctor"]} loginRole="staff">
      {(me) => (
        <DashboardShell
          area="staff"
          title="Staff desk"
          nav={items}
          me={me}
          headerExtra={
            <ToggleButton pressed={sound} onPressedChange={setSound} icon={sound ? Volume2 : VolumeX} size="sm" aria-label="Alert sound">
              <span className="hidden sm:inline">{sound ? "Sound on" : "Muted"}</span>
            </ToggleButton>
          }
        >
          <ShortcutsOverlay
            items={[["g then b", "Board"], ["g then h", "Help requests"], ["/", "Search the board"], ["?", "Show these shortcuts"]]}
            go={{ b: () => nav("/staff"), h: () => nav("/staff/help") }}
          />
          <HelpBanner items={help.data?.items ?? []} />
          <Routes>
            <Route index element={<BoardPage me={me} demo={!!cfg.data?.demoMode} />} />
            <Route path="patient" element={<PickPatient />} />
            <Route path="p/:token" element={<PatientPanel me={me} />} />
            <Route path="scans" element={<ScansPage />} />
            <Route path="help" element={<HelpPage items={help.data?.items ?? []} loading={help.isPending} />} />
          </Routes>
        </DashboardShell>
      )}
    </RequireRole>
  );
}

export default function StaffApp() {
  return <Staff />;
}

// ---------------------------------------------------------------- help
function useDismiss() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (id: number) => post(`/api/staff/help-requests/${id}/dismiss`), onSettled: () => qc.invalidateQueries({ queryKey: ["help"] }) });
}

function HelpBanner({ items }: { items: HelpRequest[] }) {
  const dismiss = useDismiss();
  const nav = useNavigate();
  if (!items.length) return null;
  return (
    <div className="mb-4 flex flex-col gap-2" role="status" aria-live="polite" data-testid="help-banner">
      {items.slice(0, 3).map((h) => (
        <div key={h.id} className="flex flex-wrap items-center gap-3 rounded-panel border border-on-marigold/30 bg-marigold px-4 py-3 text-on-marigold">
          <BellRing size={20} aria-hidden />
          <p className="flex-1 font-semibold">
            A patient at the kiosk asked for help: <span className="tabular">{h.token}</span> <span className="font-normal">at {h.at.slice(11, 16)}</span>
          </p>
          <Button size="sm" onClick={() => nav(`/staff/p/${h.token}`)}>
            Open patient
          </Button>
          <Button size="sm" icon={X} onClick={() => dismiss.mutate(h.id)}>
            Dismiss
          </Button>
        </div>
      ))}
    </div>
  );
}

function HelpPage({ items, loading }: { items: HelpRequest[]; loading: boolean }) {
  const dismiss = useDismiss();
  if (loading) return <Skeleton className="h-32" />;
  return (
    <div className="flex max-w-3xl flex-col gap-3">
      <h1 className="text-xl font-bold">Help requests</h1>
      {items.length === 0 ? (
        <EmptyState title="No one is waiting for help" icon={BellRing}>When a patient taps Call staff on the kiosk, it appears here and on every staff screen.</EmptyState>
      ) : (
        items.map((h) => (
          <div key={h.id} className="flex items-center justify-between gap-3 rounded-panel border border-line bg-surface px-4 py-3">
            <p>
              <span className="font-semibold tabular">{h.token}</span> <span className="text-muted">asked at {h.at.slice(11, 16)}</span>
            </p>
            <Button size="sm" onClick={() => dismiss.mutate(h.id)}>Mark as helped</Button>
          </div>
        ))
      )}
    </div>
  );
}

// ---------------------------------------------------------------- board
export function useBoard(q: string, status: string) {
  return useQuery({ queryKey: ["board", "today", q, status], queryFn: () => get<Board>(`/api/patients${qs({ q, status })}`), placeholderData: (p) => p });
}

function BoardPage({ me, demo }: { me: Me; demo: boolean }) {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [doc, setDoc] = useState("");
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [assignTo, setAssignTo] = useState("");
  const dq = useDebounced(q);
  const board = useBoard(dq, status);
  const doctors = useDoctors();
  const docName = (id?: string | null) => doctors.data?.find((d) => d.id === id)?.name ?? "No doctor chosen";
  const rows = useMemo(() => (board.data?.rows ?? []).filter((r) => !doc || (doc === "none" ? !r.assignedDoctor : r.assignedDoctor === doc)), [board.data, doc]);
  const urgent = rows.filter((r) => r.urgent);
  const [allUrgent, setAllUrgent] = useState(false);
  const urgentFlags = urgent
    .flatMap((r) => r.redFlags.filter((f) => f.severity === "urgent").map((f) => ({ r, f })))
    .sort((a, b) => b.r.updatedAt.localeCompare(a.r.updatedAt));
  const shownFlags = allUrgent ? urgentFlags : urgentFlags.slice(0, 3);
  // red flags seen on this screen already: only new ones get the one-off attention animation
  const seen = useRef<Set<string> | null>(null);
  const fresh = new Set<string>();
  for (const r of urgent) for (const f of r.redFlags) if (seen.current && !seen.current.has(`${r.token}:${f.ruleId}`)) fresh.add(`${r.token}:${f.ruleId}`);
  useEffect(() => {
    if (!board.data) return;
    const s = seen.current ?? new Set<string>();
    for (const r of board.data.rows) for (const f of r.redFlags) s.add(`${r.token}:${f.ruleId}`);
    seen.current = s;
  }, [board.data]);
  const assign = useMutation({
    mutationFn: async () => {
      for (const t of sel) await put(`/api/patients/${t}/doctor`, { doctorId: assignTo === "none" ? null : assignTo });
    },
    onSuccess: () => {
      setSel(new Set());
      qc.invalidateQueries({ queryKey: ["board"] });
    },
  });
  const addDemo = useMutation({ mutationFn: () => post("/api/demo/kiosk-patient"), onSuccess: () => qc.invalidateQueries({ queryKey: ["board"] }) });
  const columns: Column<BoardRow>[] = [
    { key: "q", header: "No.", cell: (r) => <span className="font-semibold tabular">{r.queueNumber ?? "-"}</span>, sortValue: (r) => r.queueNumber ?? 9999 },
    { key: "token", header: "Token", cell: (r) => <span className="font-semibold tabular">{r.token}</span>, sortValue: (r) => r.token },
    { key: "who", header: "Age, sex", cell: (r) => ageSex(r.ageYears, r.sex) },
    { key: "complaint", header: "Complaint", cell: (r) => r.complaint ?? <span className="text-muted">not given yet</span>, sortValue: (r) => r.complaint ?? "" },
    { key: "flags", header: "Red flags", sortValue: (r) => -r.redFlags.length, cell: (r) => (r.redFlags.length ? <Pill tone="red">{r.redFlags.length} urgent</Pill> : <span className="text-muted">none</span>) },
    { key: "status", header: "Status", cell: (r) => (r.status === "complete" ? "Token issued" : "On the kiosk"), sortValue: (r) => r.status },
    { key: "doctor", header: "Doctor", cell: (r) => docName(r.assignedDoctor), sortValue: (r) => docName(r.assignedDoctor) },
    { key: "vitals", header: "Vitals", cell: (r) => (r.vitalsPresent ? <Pill tone="green">taken</Pill> : <span className="font-semibold text-on-marigold">needed</span>), sortValue: (r) => (r.vitalsPresent ? 1 : 0) },
    { key: "scans", header: "Scans", cell: (r) => (r.pendingScans ? <Pill tone="marigold">{r.pendingScans} to confirm</Pill> : "") },
    { key: "wait", header: "Waiting", cell: (r) => <span className="tabular">{r.minutesWaiting} min</span>, sortValue: (r) => r.minutesWaiting },
  ];
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">Today's board</h1>
          <p className="text-sm text-muted">Red flags come from draft rules and are only a prompt to look at the patient. Not a diagnosis.</p>
        </div>
        {demo && (
          <Button icon={FlaskConical} size="sm" loading={addDemo.isPending} onClick={() => addDemo.mutate()}>
            Add synthetic chest-pain patient
          </Button>
        )}
      </div>

      <section aria-labelledby="urgent-h" className="flex flex-col gap-2">
        <h2 id="urgent-h" className="sr-only">
          Urgent red flags
        </h2>
        {shownFlags.map(({ r, f }) => (
          <RedFlagRow
            key={`${r.token}:${f.ruleId}`}
            flag={f}
            token={r.token}
            attention={fresh.has(`${r.token}:${f.ruleId}`)}
            action={
              <Button size="sm" onClick={() => nav(`/staff/p/${r.token}`)}>
                Open
              </Button>
            }
          />
        ))}
        {urgentFlags.length > 3 && (
          <Button variant="ghost" size="sm" className="self-start" onClick={() => setAllUrgent(!allUrgent)} aria-expanded={allUrgent}>
            {allUrgent ? "Show only the newest 3 urgent flags" : `Show all ${urgentFlags.length} urgent flags`}
          </Button>
        )}
      </section>

      <div className="flex flex-wrap items-end gap-3">
        <label className="relative min-w-60 flex-1">
          <span className="sr-only">Search token, number or complaint</span>
          <Search size={16} aria-hidden className="absolute left-3 top-3 text-muted" />
          <input data-shortcut="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search token, number or complaint" className="min-h-10 w-full rounded-field border border-line-strong bg-surface pl-9 pr-3" />
        </label>
        <SelectField label="Status" value={status} onChange={(e) => setStatus(e.target.value)} className="w-44">
          <option value="">All</option>
          <option value="in_progress">On the kiosk</option>
          <option value="complete">Token issued</option>
        </SelectField>
        <SelectField label="Doctor" value={doc} onChange={(e) => setDoc(e.target.value)} className="w-52">
          <option value="">All</option>
          <option value="none">No doctor chosen</option>
          {doctors.data?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </SelectField>
      </div>

      {sel.size > 0 && (
        <div className="flex flex-wrap items-end gap-3 rounded-panel border border-teal/40 bg-tint px-4 py-3">
          <p className="font-semibold">{sel.size} selected</p>
          <SelectField label="Assign to" value={assignTo} onChange={(e) => setAssignTo(e.target.value)} className="w-56">
            <option value="">Choose a doctor…</option>
            <option value="none">No doctor (reception decides)</option>
            {doctors.data?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </SelectField>
          <Button variant="primary" disabled={!assignTo} loading={assign.isPending} onClick={() => assign.mutate()}>
            Assign doctor
          </Button>
          <Button variant="ghost" onClick={() => setSel(new Set())}>Clear selection</Button>
        </div>
      )}

      {board.isPending ? (
        <div className="flex flex-col gap-2" aria-busy>
          {Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="h-10" />)}
        </div>
      ) : board.isError ? (
        <ErrorState title="Could not load the board" message={(board.error as Error).message} onRetry={() => board.refetch()} />
      ) : (
        <DataTable
          rows={rows}
          columns={columns}
          rowId={(r) => r.token}
          caption="Today's patients"
          selectable
          selected={sel}
          onSelectedChange={setSel}
          onRowClick={(r) => nav(`/staff/p/${r.token}`)}
          rowClassName={(r) => (r.urgent ? "bg-red-tint/60" : undefined)}
          empty={
            <EmptyState title={q || status || doc ? "No patient matches these filters" : "No patients yet today"}>
              {q || status || doc ? "Clear the search or filters to see everyone." : "New patients appear here as soon as they start on the kiosk."}
            </EmptyState>
          }
        />
      )}
      <p className="text-xs text-muted">Signed in as {me.username}. The board updates by itself.</p>
    </div>
  );
}

// ---------------------------------------------------------------- patient panel
function PickPatient() {
  const nav = useNavigate();
  const board = useBoard("", "");
  return (
    <div className="flex max-w-3xl flex-col gap-3">
      <h1 className="text-xl font-bold">Open a patient</h1>
      {board.isPending ? <Skeleton className="h-40" /> : (board.data?.rows.length ?? 0) === 0 ? (
        <EmptyState title="No patients yet today">New patients appear here as soon as they start on the kiosk.</EmptyState>
      ) : (
        <ul className="flex flex-col divide-y divide-line rounded-panel border border-line bg-surface">
          {board.data!.rows.map((r) => (
            <li key={r.token}>
              <button type="button" onClick={() => nav(`/staff/p/${r.token}`)} className="flex w-full items-center gap-4 px-4 py-3 text-left hover:bg-tint">
                <span className="font-semibold tabular">{r.token}</span>
                <span>{r.complaint ?? "complaint not given yet"}</span>
                {r.urgent && <Pill tone="red">urgent</Pill>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function PatientPanel({ me }: { me: Me }) {
  const { token = "" } = useParams();
  const [lang, setLang] = useState<Lang>("en");
  const qc = useQueryClient();
  const p = useQuery({ queryKey: ["patient", token, lang], queryFn: () => get<PatientView>(`/api/patients/${token}?lang=${lang}`), placeholderData: (x) => x });
  const doctors = useDoctors();
  const reassign = useMutation({
    mutationFn: (id: string) => put<PatientView>(`/api/patients/${token}/doctor`, { doctorId: id || null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["patient", token] });
      qc.invalidateQueries({ queryKey: ["board"] });
    },
  });
  if (p.isPending) return <Skeleton className="h-96" />;
  if (p.isError) return <ErrorState title="Could not open this patient" message={(p.error as Error).message} onRetry={() => p.refetch()} />;
  const pv = p.data;
  const di = pv.dosingInputs as { ageYears?: number | null; sex?: string | null; missing?: string[] };
  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h1 className="text-xl font-bold tabular">{pv.token}</h1>
        {pv.queueNumber && <p className="text-md font-semibold tabular">No. {pv.queueNumber}</p>}
        <p className="text-md">{ageSex(di.ageYears, di.sex)}</p>
        <p className="text-md font-semibold">{String(pv.complaint.label ?? "Complaint not given yet")}</p>
        <p className="text-sm text-muted">{pv.status === "complete" ? "Token issued" : "Still on the kiosk"}</p>
      </header>
      {pv.redFlags.length > 0 ? (
        <div className="flex flex-col gap-2">{pv.redFlags.map((f) => <RedFlagRow key={f.ruleId} flag={f} />)}</div>
      ) : (
        <p className="text-sm text-muted">No red flags.</p>
      )}
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <section className="rounded-panel border border-line bg-surface" aria-labelledby="ans-h">
          <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
            <h2 id="ans-h" className="text-md font-semibold">Answers</h2>
            <div role="radiogroup" aria-label="Answer language" className="inline-flex rounded-full border border-line p-0.5">
              {LANGS.map((l) => (
                <button key={l} type="button" role="radio" aria-checked={lang === l} onClick={() => setLang(l)} className={cn("min-h-8 rounded-full px-3 text-sm font-semibold", lang === l ? "bg-teal text-on-teal" : "text-muted")}>
                  {LANG_NAMES[l]}
                </button>
              ))}
            </div>
          </header>
          {di.missing && di.missing.length > 0 && <Notice tone="warn" className="m-4" title="Missing safety basics">{di.missing.join(", ")}</Notice>}
          <dl className="divide-y divide-line" lang={lang}>
            {pv.answers.map((a) => (
              <div key={a.nodeId} className="grid gap-1 px-4 py-2 sm:grid-cols-[14rem_minmax(0,1fr)]">
                <dt className="text-sm text-muted">{lang === "en" ? a.label : a.question}</dt>
                <dd className="font-semibold">{a.answer}</dd>
              </div>
            ))}
            {pv.answers.length === 0 && <p className="p-4 text-sm text-muted">No answers yet.</p>}
          </dl>
        </section>
        <div className="flex flex-col gap-6">
          <section className="rounded-panel border border-line bg-surface p-4" aria-labelledby="vit-h">
            <h2 id="vit-h" className="mb-3 text-md font-semibold">Vitals (measured)</h2>
            {Object.keys(pv.abnormal).length > 0 && (
              <Notice tone="warn" className="mb-3">Outside the usual adult range (draft thresholds): {Object.entries(pv.abnormal).map(([k, v]) => `${k} ${v}`).join(", ")}</Notice>
            )}
            <VitalsForm patient={pv} />
          </section>
          <section className="rounded-panel border border-line bg-surface p-4" aria-labelledby="doc-h">
            <h2 id="doc-h" className="mb-3 text-md font-semibold">Doctor</h2>
            <SelectField label="Assigned doctor" value={pv.assignedDoctor ?? ""} onChange={(e) => reassign.mutate(e.target.value)}>
              <option value="">No doctor chosen</option>
              {doctors.data?.map((d) => <option key={d.id} value={d.id}>{d.name}, {d.specialty.en}{d.room ? `, room ${d.room}` : ""}</option>)}
            </SelectField>
            {reassign.isSuccess && <p className="mt-2 text-sm text-green" aria-live="polite">Doctor updated.</p>}
          </section>
          <section className="rounded-panel border border-line bg-surface p-4" aria-labelledby="scan-h">
            <h2 id="scan-h" className="mb-3 text-md font-semibold">Old prescription or lab report</h2>
            <ScanUpload token={pv.token} role={me.role} />
            {pv.pendingScans.length > 0 && (
              <ul className="mt-3 text-sm">
                {pv.pendingScans.map((s) => (
                  <li key={s.id} className="flex items-center gap-2">
                    <ClipboardList size={14} aria-hidden /> {s.documentType ?? "document"} uploaded by {s.uploadedBy}, {s.items} items, waiting for the doctor
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

function ScansPage() {
  const nav = useNavigate();
  const board = useBoard("", "");
  const rows = (board.data?.rows ?? []).filter((r) => r.pendingScans > 0);
  return (
    <div className="flex max-w-3xl flex-col gap-3">
      <h1 className="text-xl font-bold">Scans</h1>
      <p className="text-sm text-muted">Open a patient to attach a photo of an old prescription or lab report to their token. A doctor confirms every scan before it is used.</p>
      {rows.length === 0 ? (
        <EmptyState title="No scans waiting for a doctor" icon={FileScan}>Scans sent to the doctor appear here until they are confirmed.</EmptyState>
      ) : (
        <ul className="flex flex-col divide-y divide-line rounded-panel border border-line bg-surface">
          {rows.map((r) => (
            <li key={r.token}>
              <button type="button" onClick={() => nav(`/staff/p/${r.token}`)} className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-tint">
                <span className="font-semibold tabular">{r.token}</span>
                <Pill tone="marigold">{r.pendingScans} waiting</Pill>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
