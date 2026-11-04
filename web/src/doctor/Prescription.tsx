import { Printer } from "lucide-react";
import type { PatientView } from "../api/client";
import { Button } from "../components/Button";
import { EmptyState } from "../components/ui";
import { ageSex } from "../lib/hooks";

type Check = Record<string, unknown>;
const text = (v: unknown) => (v === null || v === undefined || v === "" ? null : String(v));

/** Server-computed values only: the stored engine result of each confirmed check. Nothing is calculated here. */
function lines(c: Check): { medicine: string; how: string[] } {
  const r = (c.result ?? {}) as Record<string, unknown>;
  const how: string[] = [];
  const dose = [text(r.volume_ml) && `${r.volume_ml} mL`, text(r.units) && `${r.units} unit(s)`, text(r.dose_mg) && `${r.dose_mg} mg`].filter(Boolean).join(" = ");
  if (dose) how.push(`${dose} per dose`);
  if (r.interval_h) how.push(`every ${r.interval_h} hours`);
  if (r.doses_per_day) how.push(`${r.doses_per_day} times a day`);
  if (r.duration) how.push(`for ${r.duration}`);
  if (r.text_regimen) how.push(String(r.text_regimen));
  const product = text(r.product);
  return { medicine: `${c.drug}${product ? `, ${product}` : ""}`, how };
}

export function Prescription({ pv }: { pv: PatientView }) {
  const checks = ((pv.dosingChecks ?? []) as Check[]).filter((c) => c.status === "ok");
  if (!checks.length)
    return <EmptyState title="No prescription yet">Confirm a dosage check (status ok) in Dosage check. The prescription is built from the confirmed checks and appears here.</EmptyState>;
  const last = checks[checks.length - 1];
  return (
    <div className="flex max-w-3xl flex-col gap-3">
      <div className="no-print flex items-center gap-3">
        <Button icon={Printer} onClick={() => window.print()}>Print prescription</Button>
        <span className="text-sm text-muted">Draft for the doctor to review and sign.</span>
      </div>
      <article className="rx-area rounded-panel border border-line bg-white p-6 text-black" aria-label="Prescription">
        <header className="border-b border-black pb-2">
          <h2 className="text-lg font-bold">Prescription</h2>
          <p className="text-sm">
            Patient {pv.token} · {ageSex(pv.dosingInputs.ageYears as number | null, pv.dosingInputs.sex as string | null)} · {String(last.at).slice(0, 10)}
          </p>
          {pv.complaint.label ? <p className="text-sm">Complaint: {String(pv.complaint.label)}</p> : null}
        </header>
        <ol className="my-4 flex list-decimal flex-col gap-3 pl-5">
          {checks.map((c, i) => {
            const { medicine, how } = lines(c);
            const cats = (c.overrideCategories as string[]) ?? [];
            return (
              <li key={i}>
                <p className="font-semibold">{medicine}</p>
                {c.indication ? <p className="text-sm">For: {String(c.indication)}</p> : null}
                {how.length > 0 && <p className="text-sm">{how.join(", ")}</p>}
                {cats.length > 0 && <p className="text-sm font-bold">Safety override recorded: {((c.overrideReasons as string[]) ?? []).join("; ")}</p>}
              </li>
            );
          })}
        </ol>
        <footer className="border-t border-black pt-2 text-xs">
          <p>Doctor: {String(last.doctorId)}. Signature: ______________________</p>
          <p>Prototype data, not clinically verified. Decision support only; the doctor decides.</p>
        </footer>
      </article>
    </div>
  );
}
