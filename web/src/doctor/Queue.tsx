import { useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Search, Siren } from "lucide-react";
import { get, qs, type Board, type BoardRow, type Me } from "../api/client";
import { Button } from "../components/Button";
import { DataTable, type Column } from "../components/DataTable";
import { EmptyState, ErrorState, Pill, Skeleton } from "../components/ui";
import { ageSex, useDebounced, useDoctors } from "../lib/hooks";

export function Queue({ me }: { me: Me }) {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const dq = useDebounced(q);
  const board = useQuery({ queryKey: ["board", "today", dq], queryFn: () => get<Board>(`/api/patients${qs({ q: dq })}`), placeholderData: (p) => p });
  const doctors = useDoctors();
  const name = (id?: string | null) => doctors.data?.find((d) => d.id === id)?.name ?? "No doctor chosen";
  const rows = board.data?.rows ?? [];
  const mine = rows.filter((r) => r.mine);
  const next = (mine.length ? mine : rows).find((r) => r.status === "complete") ?? (mine.length ? mine : rows)[0];
  const open = (r: BoardRow) => nav(`/doctor/p/${r.token}`);
  const columns: Column<BoardRow>[] = useMemo(
    () => [
      { key: "q", header: "No.", cell: (r) => <span className="font-semibold tabular">{r.queueNumber ?? "-"}</span>, sortValue: (r) => r.queueNumber ?? 9999 },
      { key: "token", header: "Token", cell: (r) => <span className="font-semibold tabular">{r.token}</span>, sortValue: (r) => r.token },
      { key: "who", header: "Age, sex", cell: (r) => ageSex(r.ageYears, r.sex) },
      { key: "complaint", header: "Complaint", cell: (r) => r.complaint ?? <span className="text-muted">not given yet</span>, sortValue: (r) => r.complaint ?? "" },
      {
        key: "flags", header: "Red flags", sortValue: (r) => (r.urgent ? 0 : 1),
        cell: (r) => (r.redFlags.length ? <Pill tone="red" icon={Siren}>{r.redFlags.length} urgent</Pill> : <span className="text-muted">none</span>),
      },
      { key: "doc", header: "Doctor", cell: (r) => (r.mine ? <span className="font-semibold">You</span> : name(r.assignedDoctor)) },
      { key: "status", header: "Status", cell: (r) => (r.status === "complete" ? "Ready" : "On the kiosk"), sortValue: (r) => r.status },
      { key: "wait", header: "Waiting", cell: (r) => <span className="tabular">{r.minutesWaiting} min</span>, sortValue: (r) => r.minutesWaiting },
    ],
    [doctors.data],
  );
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">My queue</h1>
          <p className="text-sm text-muted">{me.doctorId ? "Your patients first, then urgent red flags." : "Today's patients, urgent red flags first. This login is not linked to a doctor in doctors.json."}</p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <label className="relative">
            <span className="sr-only">Search token or complaint</span>
            <Search size={16} aria-hidden className="absolute left-3 top-3 text-muted" />
            <input data-shortcut="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search token or complaint" className="min-h-10 w-64 rounded-field border border-line-strong bg-surface pl-9 pr-3" />
          </label>
          <Button variant="primary" iconRight={ArrowRight} disabled={!next} onClick={() => next && open(next)} data-shortcut="next">
            Next patient
          </Button>
        </div>
      </div>
      {board.isPending ? (
        <Skeleton className="h-64" />
      ) : board.isError ? (
        <ErrorState title="Could not load the queue" message={(board.error as Error).message} onRetry={() => board.refetch()} />
      ) : (
        <DataTable
          rows={rows}
          columns={columns}
          rowId={(r) => r.token}
          caption="Today's patients"
          onRowClick={open}
          rowClassName={(r) => (r.urgent ? "bg-red-tint/60" : r.mine ? "bg-tint/40" : undefined)}
          empty={<EmptyState title="No patients yet today">New patients appear here as soon as they start on the kiosk. In demo mode, use Load demo patient.</EmptyState>}
        />
      )}
    </div>
  );
}
