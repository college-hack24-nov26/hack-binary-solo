import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { FlaskConical } from "lucide-react";
import { get, post, type Fixture } from "../api/client";
import { Button } from "../components/Button";
import { ErrorState, Notice, Skeleton } from "../components/ui";

/** DEMO_MODE only: replay a synthetic fixture through the real quiz session, then open its Dosage check. */
export function DemoLoader() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const fx = useQuery({ queryKey: ["demo-fixtures"], queryFn: () => get<Fixture[]>("/api/demo/fixtures"), retry: false });
  const load = useMutation({
    mutationFn: (f: Fixture) => post<{ token: string }>(`/api/demo/load/${f.key}`).then((r) => ({ ...r, f })),
    onSuccess: ({ token, f }) => {
      qc.invalidateQueries({ queryKey: ["patient", token] });
      qc.invalidateQueries({ queryKey: ["history-items", token] });
      qc.invalidateQueries({ queryKey: ["board"] });
      nav(`/doctor/p/${token}/dosage`, { state: { preset: { drug: f.drug, indication: f.indication } } });
    },
  });
  if (fx.isPending) return <Skeleton className="h-48" />;
  if (fx.isError) return <ErrorState title="Demo patients are not available" message="Start the server with DEMO_MODE=1 to load synthetic demo patients." />;
  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <h1 className="text-xl font-bold">Load demo patient</h1>
      <Notice>Synthetic patients only. The quiz answers are replayed through the real intake session, so red flags and the record are exactly what the kiosk would produce. Loading again resets that patient.</Notice>
      <ul className="flex flex-col gap-3">
        {fx.data.map((f) => (
          <li key={f.key} className="flex flex-wrap items-center justify-between gap-3 rounded-panel border border-line bg-surface p-4">
            <div>
              <p className="font-semibold">{f.displayName} <span className="font-normal text-muted tabular">{f.token}</span></p>
              <p className="text-sm">{f.title.replace(/^[A-C]\.\s*/, "")}</p>
            </div>
            <Button icon={FlaskConical} variant="primary" loading={load.isPending && load.variables?.key === f.key} onClick={() => load.mutate(f)} data-testid={`load-${f.key}`}>
              Load and open dosage check
            </Button>
          </li>
        ))}
      </ul>
      {load.isError && <Notice tone="stop">{(load.error as Error).message}</Notice>}
    </div>
  );
}
