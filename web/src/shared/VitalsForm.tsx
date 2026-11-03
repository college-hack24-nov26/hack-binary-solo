import { useActionState, useEffect, useRef } from "react";
import { useFormStatus } from "react-dom";
import { useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { Save } from "lucide-react";
import { ApiError, put, type PatientView } from "../api/client";
import { Button } from "../components/Button";
import { Notice, TextField } from "../components/ui";

// Same bounds as records.schema.Vitals (the server re-validates; this copy only gives faster feedback)
const FIELDS = [
  { key: "bpSystolic", label: "BP systolic", suffix: "mmHg", min: 40, max: 300, int: true },
  { key: "bpDiastolic", label: "BP diastolic", suffix: "mmHg", min: 20, max: 200, int: true },
  { key: "pulse", label: "Pulse", suffix: "/min", min: 20, max: 250, int: true },
  { key: "tempC", label: "Temperature", suffix: "°C", min: 30, max: 45, int: false },
  { key: "spo2", label: "SpO2", suffix: "%", min: 50, max: 100, int: true },
  { key: "respRate", label: "Respiratory rate", suffix: "/min", min: 4, max: 80, int: true },
  { key: "weightKg", label: "Weight", suffix: "kg", min: 0.1, max: 400, int: false },
  { key: "heightCm", label: "Height", suffix: "cm", min: 30, max: 250, int: false },
  { key: "bloodGlucose", label: "Blood glucose", suffix: "mg/dL", min: 10, max: 900, int: false },
] as const;
type Key = (typeof FIELDS)[number]["key"];
type State = { errors?: Partial<Record<Key | "notes" | "form", string>>; values?: Record<string, string>; saved?: string };

const fieldSchema = (f: (typeof FIELDS)[number]) =>
  z
    .string()
    .trim()
    .transform((v) => (v === "" ? null : Number(v)))
    .refine((v) => v === null || !Number.isNaN(v), "Enter a number.")
    .refine((v) => v === null || !f.int || Number.isInteger(v), "Enter a whole number.")
    .refine((v) => v === null || (v >= f.min && v <= f.max), `Enter a value from ${f.min} to ${f.max}.`);

function Submit() {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" variant="primary" icon={Save} loading={pending}>
      Save vitals
    </Button>
  );
}

/** Staff (and doctor) enter measured vitals. A save replaces the previous set, as on the Streamlit staff page. */
export function VitalsForm({ patient }: { patient: PatientView }) {
  const qc = useQueryClient();
  const v = (patient.vitals ?? {}) as Record<string, unknown>;
  const formRef = useRef<HTMLFormElement>(null);
  const [state, action] = useActionState<State, FormData>(async (_p, fd) => {
    const values = Object.fromEntries([...FIELDS.map((f) => [f.key, String(fd.get(f.key) ?? "")]), ["notes", String(fd.get("notes") ?? "")]]);
    const errors: State["errors"] = {};
    const body: Record<string, number | string | null> = { notes: values.notes!.trim() };
    for (const f of FIELDS) {
      const r = fieldSchema(f).safeParse(values[f.key]);
      if (!r.success) errors[f.key] = r.error.issues[0]?.message;
      else body[f.key] = r.data;
    }
    if (!errors.bpSystolic && !errors.bpDiastolic && body.bpSystolic && body.bpDiastolic && Number(body.bpSystolic) <= Number(body.bpDiastolic))
      errors.bpSystolic = "Systolic must be higher than diastolic.";
    if (Object.keys(errors).length) return { errors, values };
    try {
      const pv = await put<PatientView>(`/api/patients/${patient.token}/vitals`, body);
      qc.setQueryData(["patient", patient.token, "en"], pv);
      qc.invalidateQueries({ queryKey: ["patient", patient.token] });
      qc.invalidateQueries({ queryKey: ["board"] });
      return { saved: "Vitals saved. The doctor can see them now." };
    } catch (e) {
      if (e instanceof ApiError && e.fields.length) return { errors: e.fieldMap() as State["errors"], values };
      return { errors: { form: e instanceof Error ? e.message : "Vitals were not saved." }, values };
    }
  }, {});
  useEffect(() => {
    const first = state.errors && Object.keys(state.errors)[0];
    if (first) formRef.current?.querySelector<HTMLElement>(`[name="${first}"]`)?.focus();
  }, [state]);
  const val = (k: string) => state.values?.[k] ?? (v[k] === null || v[k] === undefined ? "" : String(v[k]));
  return (
    <form ref={formRef} action={action} noValidate className="flex flex-col gap-4" key={String(patient.vitals?.recordedAt ?? "new")}>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {FIELDS.map((f) => (
          <TextField key={f.key} name={f.key} label={f.label} suffix={f.suffix} inputMode="decimal" defaultValue={val(f.key)} error={state.errors?.[f.key]} />
        ))}
      </div>
      <TextField name="notes" label="Notes (for example fasting, arm used, taken after rest)" defaultValue={val("notes")} error={state.errors?.notes} />
      <div aria-live="polite">
        {state.saved && <Notice tone="ok">{state.saved}</Notice>}
        {state.errors?.form && <Notice tone="stop">{state.errors.form}</Notice>}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Submit />
        {Boolean(patient.vitals?.recordedAt) && (
          <span className="text-xs text-muted">
            Last saved {String(patient.vitals?.recordedAt).slice(0, 16).replace("T", " ")} by {String(patient.vitals?.recordedBy)}
          </span>
        )}
      </div>
    </form>
  );
}

export const VITAL_FIELDS = FIELDS;
