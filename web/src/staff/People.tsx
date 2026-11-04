import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Lock, Search, UserPlus } from "lucide-react";
import { Link } from "react-router";
import { api, get, qs, type Schemas } from "../api/client";
import { Button } from "../components/Button";
import { EmptyState, ErrorState, Notice, Pill, SelectField, TextField } from "../components/ui";
import { useDebounced } from "../lib/hooks";

type Patient = Schemas["PatientAdminOut"];

/**
 * Patient lookup for the desk. Numbers are shown masked; type the last digits, a token or a queue number, or the full number (it is
 * hashed on the server and never echoed). Reset PIN shows a temporary PIN once. "Complete walk-in" attaches a number to a patient
 * who chose "Ask staff" at the kiosk.
 */
export function PeoplePage() {
  const [q, setQ] = useState("");
  const dq = useDebounced(q);
  const list = useQuery({ queryKey: ["people", dq], queryFn: () => get<{ patients: Patient[] }>(`/api/staff/patients${qs({ q: dq })}`), placeholderData: (x) => x });
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-bold">Patients</h1>
      <div className="relative max-w-xl">
        <Search size={18} aria-hidden className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
        <input aria-label="Find a patient by the last digits, token, queue number or full number" placeholder="Last digits, token or queue number" value={q} onChange={(e) => setQ(e.target.value)}
          className="min-h-10 w-full rounded-field border border-line-strong bg-surface pl-10 pr-3" data-testid="people-search" />
      </div>
      {list.isError && <ErrorState title="Could not load patients" message={(list.error as Error).message} onRetry={() => list.refetch()} />}
      {list.data && list.data.patients.length === 0 && <EmptyState title="No patient found">Try the last 3 or 4 digits, or the visit token.</EmptyState>}
      <ul className="flex flex-col gap-3">
        {list.data?.patients.map((p) => <PersonRow key={p.id} p={p} />)}
      </ul>
    </div>
  );
}

function PersonRow({ p }: { p: Patient }) {
  const qc = useQueryClient();
  const [pin, setPin] = useState<string | null>(null);
  const [type, setType] = useState<"mobile" | "abha">("mobile");
  const [num, setNum] = useState("");
  const refresh = () => qc.invalidateQueries({ queryKey: ["people"] });
  const reset = useMutation({ mutationFn: () => api<{ pin: string }>(`/api/staff/patients/${p.id}/reset-pin`, { method: "POST", body: {} }), onSuccess: (r) => { setPin(r.pin); refresh(); } });
  const complete = useMutation({
    mutationFn: () => api<{ pin: string }>(`/api/staff/patients/${p.id}/walk-in-complete`, { method: "POST", body: { type, identifier: num } }),
    onSuccess: (r) => { setPin(r.pin); setNum(""); refresh(); },
  });
  return (
    <li className="rounded-panel border border-line bg-surface p-4" data-testid="person-row">
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-md font-semibold tabular" data-testid="person-masked">{p.masked}</p>
        <Pill tone="neutral">{p.identifierType === "walk_in" ? "Walk-in" : p.identifierType === "abha" ? "ABHA number (unchecked)" : "Mobile"}</Pill>
        {p.needsStaff && <Pill tone="marigold">Needs the desk</Pill>}
        {p.locked && <Pill tone="red" icon={Lock}>Locked</Pill>}
        <span className="text-sm text-muted">{p.visitIds.length} visit{p.visitIds.length === 1 ? "" : "s"}</span>
        <div className="ml-auto flex flex-wrap gap-2">
          {p.visitIds.slice(-2).map((v) => <Link key={v} to={`/staff/p/${v}`} className="text-sm font-semibold text-teal underline">{v}</Link>)}
          {p.identifierType !== "walk_in" && (
            <Button size="sm" icon={KeyRound} loading={reset.isPending} onClick={() => reset.mutate()} data-testid="reset-pin">Reset PIN</Button>
          )}
        </div>
      </div>
      {pin && (
        <Notice tone="ok" title="Temporary PIN (shown once)" className="mt-3">
          <span className="text-xl font-bold tabular" data-testid="temp-pin">{pin}</span>
          <span className="ml-3">Tell the patient in person after checking who they are. It is not stored or shown again.</span>
        </Notice>
      )}
      {reset.isError && <Notice tone="stop" className="mt-3">{(reset.error as Error).message}</Notice>}
      {p.identifierType === "walk_in" && (
        <form className="mt-4 grid items-end gap-3 sm:grid-cols-[10rem_minmax(0,1fr)_auto]" onSubmit={(e) => { e.preventDefault(); complete.mutate(); }} aria-label="Complete walk-in">
          <SelectField label="Number type" value={type} onChange={(e) => setType(e.target.value as "mobile" | "abha")}>
            <option value="mobile">Mobile number</option>
            <option value="abha">ABHA number (optional)</option>
          </SelectField>
          <TextField label="Number" inputMode="numeric" autoComplete="off" value={num} onChange={(e) => setNum(e.target.value)} error={complete.isError ? (complete.error as Error).message : undefined} />
          <Button type="submit" variant="primary" icon={UserPlus} loading={complete.isPending} disabled={!num.trim()} data-testid="walkin-complete">Complete walk-in</Button>
        </form>
      )}
    </li>
  );
}
