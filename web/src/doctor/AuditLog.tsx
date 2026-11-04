import { useEffect, useMemo, useRef, useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { get, qs, type AuditDetail, type AuditPage, type AuditRow, type AuditVerify } from "../api/client";
import { buttonClass } from "../components/Button";
import { ChainSeal, HashLink } from "../components/AuditChain";
import { DataTable, type Column } from "../components/DataTable";
import { EmptyState, ErrorState, Notice, SelectField, Skeleton, TextField } from "../components/ui";
import { Disclosure } from "../dosing/ResultCard";
import { cn } from "../lib/cn";

type Filters = { patient: string; drug: string; action: string; from: string; to: string };

/** Read-only audit log: newest first, infinite (cursor pages), filters, chain status, row details, export. No edit or delete. */
export function AuditLog() {
  const [f, setF] = useState<Filters>({ patient: "", drug: "", action: "", from: "", to: "" });
  const verify = useQuery({ queryKey: ["audit", "verify"], queryFn: () => get<AuditVerify>("/api/audit/verify") });
  const params = { patient: f.patient, drug: f.drug, action: f.action, from: f.from, to: f.to };
  const pages = useInfiniteQuery({
    queryKey: ["audit", "rows", params],
    queryFn: ({ pageParam, signal }) => get<AuditPage>(`/api/audit${qs({ ...params, cursor: pageParam, limit: 50 })}`, signal),
    initialPageParam: "",
    getNextPageParam: (last) => last.nextCursor ?? undefined,
  });
  const rows = useMemo(() => pages.data?.pages.flatMap((p) => p.rows) ?? [], [pages.data]);
  const first = pages.data?.pages[0];
  const sentinel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    const io = new IntersectionObserver((e) => {
      // one request at a time: no double fetch, and a failed page stops until "Try again" (rows already shown stay)
      if (e[0]?.isIntersecting && pages.hasNextPage && !pages.isFetchingNextPage && !pages.isFetchNextPageError) pages.fetchNextPage();
    }, { rootMargin: "400px" });
    io.observe(el);
    return () => io.disconnect();
  }, [pages]);
  const bad = verify.data && !verify.data.ok ? verify.data.firstBadIndex : null;
  const columns: Column<AuditRow>[] = [
    { key: "time", header: "Time", cell: (r) => <span className="whitespace-nowrap tabular">{r.time.slice(0, 19).replace("T", " ")}</span> },
    {
      key: "action", header: "Action",
      cell: (r) => <span className={cn("font-semibold", r.event === "override" && "text-red")}>{r.action}</span>,
    },
    { key: "patient", header: "Patient", cell: (r) => <span className="tabular">{r.patient}</span> },
    { key: "drug", header: "Drug", cell: (r) => r.drug },
    { key: "status", header: "Status", cell: (r) => r.status ?? "-" },
    { key: "doctor", header: "Doctor", cell: (r) => r.doctor },
    { key: "hash", header: "Hash, linked to previous", cell: (r) => <HashLink hash={r.hash} prev={r.prev} bad={bad === r.index} /> },
  ];
  const nextFailed = pages.isFetchNextPageError;
  const retryNext = () => pages.fetchNextPage();
  const exportUrl = (fmt: "json" | "csv") => `/api/audit/export${qs({ ...params, format: fmt })}`;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">Audit log</h1>
          <p className="text-sm text-muted">Read-only. Every dosage evaluation, confirmation, override and History check answer, newest first.</p>
        </div>
        {verify.isError ? <Notice tone="stop">Could not verify the chain: {(verify.error as Error).message}</Notice> : <ChainSeal ok={verify.data?.ok} entries={verify.data?.entries} firstBad={verify.data?.firstBadIndex} />}
      </div>
      <section className="grid gap-3 rounded-panel border border-line bg-surface p-4 sm:grid-cols-3 lg:grid-cols-6" aria-label="Filters">
        <SelectField label="Patient" value={f.patient} onChange={(e) => setF({ ...f, patient: e.target.value })}>
          <option value="">All</option>
          {first?.facets.patients?.map((p) => <option key={p}>{p}</option>)}
        </SelectField>
        <SelectField label="Drug" value={f.drug} onChange={(e) => setF({ ...f, drug: e.target.value })}>
          <option value="">All</option>
          {first?.facets.drugs?.map((p) => <option key={p}>{p}</option>)}
        </SelectField>
        <SelectField label="Action" value={f.action} onChange={(e) => setF({ ...f, action: e.target.value })}>
          <option value="">All</option>
          {first?.facets.actions?.map((p) => <option key={p}>{p}</option>)}
        </SelectField>
        <TextField label="From" type="date" value={f.from} onChange={(e) => setF({ ...f, from: e.target.value })} />
        <TextField label="To" type="date" value={f.to} onChange={(e) => setF({ ...f, to: e.target.value })} />
        <div className="flex items-end gap-2">
          <a className={buttonClass("secondary", "md")} href={exportUrl("json")} download>
            <Download size={16} aria-hidden /> JSON
          </a>
          <a className={buttonClass("secondary", "md")} href={exportUrl("csv")} download>
            <Download size={16} aria-hidden /> CSV
          </a>
        </div>
      </section>
      {first && (
        <p className="text-sm tabular" aria-live="polite">
          <span className="font-semibold">{first.total}</span> of {first.totalAll} entries match. Exports contain every matching entry.
        </p>
      )}
      {pages.isPending ? (
        <Skeleton className="h-96" />
      ) : pages.isError ? (
        <ErrorState title="Could not load the audit log" message={(pages.error as Error).message} onRetry={() => pages.refetch()} />
      ) : (
        <DataTable
          rows={rows}
          columns={columns}
          rowId={(r) => String(r.index)}
          caption="Audit log entries, newest first"
          expand={(r) => <EntryDetail index={r.index} />}
          rowClassName={(r) => (bad === r.index ? "bg-red-tint outline-2 -outline-offset-2 outline-red" : undefined)}
          empty={<EmptyState title="No audit entries match">Every dosage check run on the Dosage check screen is written here.</EmptyState>}
          footer={
            <div ref={sentinel} className="border-t border-line px-4 py-3 text-sm text-muted">
              {pages.isFetchingNextPage ? (
                "Loading older entries…"
              ) : nextFailed ? (
                <span className="flex items-center gap-3 text-red">
                  Older entries did not load.
                  <button type="button" className={buttonClass("secondary", "sm")} onClick={retryNext}>
                    Try again
                  </button>
                </span>
              ) : pages.hasNextPage ? (
                "Scroll for older entries"
              ) : (
                "Start of the log."
              )}
            </div>
          }
        />
      )}
    </div>
  );
}

function EntryDetail({ index }: { index: number }) {
  const q = useQuery({ queryKey: ["audit", "entry", index], queryFn: () => get<AuditDetail>(`/api/audit/entries/${index}`), staleTime: Infinity });
  if (q.isPending) return <Skeleton className="h-24" />;
  if (q.isError) return <ErrorState title="Could not load this entry" message={(q.error as Error).message} onRetry={() => q.refetch()} />;
  const d = q.data.detail as Record<string, unknown>;
  const list = (k: string) => ((d[k] as unknown[]) ?? []).map((x) => (typeof x === "string" ? x : JSON.stringify(x)));
  return (
    <div className="flex flex-col gap-3 text-sm">
      {(d.override_category || d.override_reason) ? (
        <p>
          <span className="font-bold text-red">Override</span> category {String(d.override_category ?? "-")}, reason “{String(d.override_reason ?? "")}”
          {d.overridden_block ? `, block: ${String(d.overridden_block)}` : ""}
        </p>
      ) : null}
      {(["calculation_steps", "warnings", "interactions", "blocks"] as const).map((k) =>
        list(k).length ? (
          <div key={k}>
            <p className="font-semibold">{k.replace("_", " ").replace(/^./, (c) => c.toUpperCase())}</p>
            <ol className={cn("pl-5", k === "calculation_steps" ? "list-decimal" : "list-disc")}>
              {list(k).map((x, i) => <li key={i}>{x}</li>)}
            </ol>
          </div>
        ) : null,
      )}
      {list("sources").length > 0 && (
        <div>
          <p className="font-semibold">Sources</p>
          <ul className="list-disc pl-5">
            {((d.sources as Record<string, string>[]) ?? []).map((s, i) => (
              <li key={i}>{s.id ?? "-"} {s.name} {s.url && <span className="break-all text-muted">{s.url}</span>}</li>
            ))}
          </ul>
        </div>
      )}
      <Disclosure summary="Inputs">
        <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-xs">{JSON.stringify(d.inputs, null, 1)}</pre>
      </Disclosure>
      <Disclosure summary="Provenance">
        <pre className="max-h-80 overflow-auto whitespace-pre-wrap font-mono text-xs">{JSON.stringify(d.provenance, null, 1)}</pre>
      </Disclosure>
      <p className="break-all font-mono text-xs text-muted">hash {q.data.hash}, previous {q.data.prev}</p>
    </div>
  );
}
