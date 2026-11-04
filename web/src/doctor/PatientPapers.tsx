import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CalendarClock, FilePlus2 } from "lucide-react";
import { Link } from "react-router";
import { api, get, type Schemas } from "../api/client";
import { Button } from "../components/Button";
import { EmptyState, ErrorState, Notice, Pill, Skeleton } from "../components/ui";

type Papers = Schemas["DoctorScansOut"];
type Previous = Schemas["PreviousVisitsOut"];

/**
 * What the patient scanned at the kiosk. The text is patient-supplied and unverified: the label is on the panel and on every paper,
 * next to the picture. Nothing here reaches the dosage check until the doctor presses "Use as current medicines", which records
 * the doctor's name and a provenance on every item.
 */
export function PatientPapers({ token }: { token: string }) {
  const qc = useQueryClient();
  const papers = useQuery({ queryKey: ["papers", token], queryFn: () => get<Papers>(`/api/doctor/visits/${token}/scans`) });
  const prev = useQuery({ queryKey: ["previous", token], queryFn: () => get<Previous>(`/api/doctor/visits/${token}/previous`) });
  const use = useMutation({
    mutationFn: (sid: string) => api<{ added: number }>(`/api/doctor/visits/${token}/scans/${sid}/use-as-current-medicines`, { method: "POST", body: {} }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["papers", token] });
      qc.invalidateQueries({ queryKey: ["timeline", token] });
    },
  });
  return (
    <section className="flex flex-col gap-4" aria-labelledby="papers-h" data-testid="patient-papers">
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="papers-h" className="text-lg font-semibold">Patient papers</h2>
        <Pill tone="marigold" icon={AlertTriangle}>Patient-supplied, unverified text</Pill>
        {papers.data?.patientMasked && <span className="text-sm text-muted tabular">{papers.data.patientMasked}</span>}
      </div>
      {papers.isPending ? (
        <Skeleton className="h-32" />
      ) : papers.isError ? (
        <ErrorState title="Could not load the patient's papers" message={(papers.error as Error).message} onRetry={() => papers.refetch()} />
      ) : papers.data.scans.length === 0 ? (
        <EmptyState title="The patient did not scan any papers" />
      ) : (
        papers.data.scans.map((s) => (
          <article key={s.id} className="grid gap-4 rounded-panel border border-line bg-surface p-4 md:grid-cols-[12rem_minmax(0,1fr)]" data-testid="paper">
            <div>
              {s.hasImage ? (
                <a href={`/api/doctor/visits/${token}/scans/${s.id}/image`} target="_blank" rel="noreferrer" aria-label="Open the picture the patient took">
                  <img src={`/api/doctor/visits/${token}/scans/${s.id}/image`} alt="Picture of the paper the patient scanned" className="w-full rounded-field border border-line" />
                </a>
              ) : (
                <p className="rounded-field bg-tint p-3 text-sm text-muted">The picture was deleted after the patient confirmed.</p>
              )}
            </div>
            <div className="flex min-w-0 flex-col gap-2">
              <p className="font-semibold">
                {String(s.docType ?? "paper").replace("_", " ")} <span className="font-normal text-muted tabular">{s.docDate ?? "no date read"}</span>
              </p>
              <p className="text-xs font-semibold text-muted" data-testid="unverified-label">{s.label}{s.confirmedByPatient ? ", checked by the patient" : ", not checked by the patient"}</p>
              {s.medicines.length === 0 ? (
                <p className="text-sm text-muted">No medicines were read or typed.</p>
              ) : (
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-xs text-muted"><th className="px-2 py-1">Medicine</th><th className="px-2 py-1">Strength</th><th className="px-2 py-1">How often</th></tr></thead>
                  <tbody>
                    {s.medicines.map((m, i) => (
                      <tr key={i} className="border-t border-line">
                        <td className="px-2 py-1 font-semibold">{String(m.name ?? "")}</td>
                        <td className="px-2 py-1">{String(m.dose ?? "") || <span className="text-muted">not read</span>}</td>
                        <td className="px-2 py-1">{String(m.frequency ?? "") || <span className="text-muted">not read</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {s.freeText && <p className="whitespace-pre-line rounded-field bg-tint px-3 py-2 text-sm">{s.freeText}</p>}
              <div className="flex flex-wrap items-center gap-3">
                <Button variant="primary" size="sm" icon={FilePlus2} disabled={!!s.usedByDoctor || s.medicines.length === 0} loading={use.isPending && use.variables === s.id} onClick={() => use.mutate(s.id)} data-testid="use-meds">
                  Use as current medicines
                </Button>
                {s.usedByDoctor && <span className="text-sm text-green" data-testid="used-by">Used by {s.usedByDoctor}. Items carry the label "patient scan, unverified, doctor used".</span>}
              </div>
            </div>
          </article>
        ))
      )}
      {use.isError && <Notice tone="stop">{(use.error as Error).message}</Notice>}
      {prev.data && prev.data.visits.length > 0 && (
        <div data-testid="previous-visits">
          <h3 className="mb-2 flex items-center gap-2 text-md font-semibold"><CalendarClock size={18} aria-hidden />Previous visits</h3>
          <ol className="divide-y divide-line rounded-panel border border-line bg-surface text-sm">
            {prev.data.visits.map((v) => (
              <li key={v.token} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2">
                <span className="font-semibold tabular">{v.date}</span>
                <span>{v.complaint ?? "complaint not given"}</span>
                <span className="text-muted tabular">token {v.queueNumber ?? "-"}</span>
                <Link to={`/doctor/p/${v.token}`} className="ml-auto font-semibold text-teal underline">{v.token}</Link>
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}
