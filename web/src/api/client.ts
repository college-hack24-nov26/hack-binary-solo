// Thin fetch wrapper. Same origin only; every mutating call carries the CSRF header the server requires.
import type { components } from "./generated";

export type Schemas = components["schemas"];
export type KioskScreen = Schemas["KioskScreen"];
export type KioskCreated = Schemas["KioskCreated"];
export type TokenSlip = Schemas["TokenSlip"];
export type ReviewItem = Schemas["ReviewItem"];
export type DoctorOut = Schemas["DoctorOut"];
export type BodyRegions = Schemas["BodyRegions"];
export type Region = Schemas["Region"];
export type Me = Schemas["Me"];
export type SystemConfig = Schemas["SystemConfig"];
export type OfflineStatus = Schemas["OfflineStatus"];
export type BoardRow = Schemas["BoardRow"];
export type Board = Schemas["Board"];
export type PatientView = Schemas["PatientView"];
export type RedFlag = Schemas["RedFlagOut"];
export type VitalsIn = Schemas["VitalsIn"];
export type HelpRequest = Schemas["HelpRequest"];
export type SummaryOut = Schemas["SummaryOut"];
export type Timeline = Schemas["Timeline"];
export type Drugs = Schemas["Drugs"];
export type Drug = Schemas["Drug"];
export type HistoryItems = Schemas["HistoryItems"];
export type HistoryItem = Schemas["HistoryItem"];
export type EvaluateIn = Schemas["EvaluateIn"];
export type Evaluation = Schemas["Evaluation"];
export type Card = Schemas["Card"];
export type MissingItem = Schemas["MissingItem"];
export type AuditPage = Schemas["AuditPage"];
export type AuditRow = Schemas["AuditRow"];
export type AuditVerify = Schemas["AuditVerify"];
export type AuditDetail = Schemas["AuditDetail"];
export type Fixture = Schemas["Fixture"];
export type PendingScan = Schemas["PendingScanOut"];
export type IdentityOut = Schemas["IdentityOut"];
export type ScanOut = Schemas["ScanOut"];
export type ScanMedicine = Schemas["ScanMedicine"];
export type ScanField = Schemas["ScanField"];

export type FieldError = { loc: (string | number)[]; msg: string; type: string };

export class ApiError extends Error {
  status: number;
  fields: FieldError[];
  /** Machine code from the X-Error-Code header (e.g. wrong_pin, locked), so the kiosk can answer in the patient's language. */
  code: string | null;
  attemptsLeft: number | null;
  constructor(status: number, message: string, fields: FieldError[] = [], code: string | null = null, attemptsLeft: number | null = null) {
    super(message);
    this.status = status;
    this.fields = fields;
    this.code = code;
    this.attemptsLeft = attemptsLeft;
  }
  /** field name -> message, from a FastAPI 422 body */
  fieldMap(): Record<string, string> {
    const out: Record<string, string> = {};
    for (const f of this.fields) {
      const key = String(f.loc[f.loc.length - 1] ?? "");
      if (key && !out[key]) out[key] = f.msg.replace(/^Value error, /, "");
    }
    return out;
  }
}

type Opts = { method?: string; body?: unknown; headers?: Record<string, string>; form?: FormData; signal?: AbortSignal };

export async function api<T>(path: string, opts: Opts = {}): Promise<T> {
  const method = opts.method ?? (opts.body !== undefined || opts.form ? "POST" : "GET");
  const headers: Record<string, string> = { Accept: "application/json", ...opts.headers };
  if (method !== "GET") headers["X-Requested-With"] = "medikiosk";
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  let res: Response;
  try {
    res = await fetch(path, { method, headers, body, credentials: "same-origin", signal: opts.signal });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError(0, "The server did not answer. Check that the clinic computer is on and connected to this network.");
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = undefined;
  try {
    data = text ? JSON.parse(text) : undefined;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const code = res.headers.get("X-Error-Code");
    const left = res.headers.get("X-Attempts-Left");
    const detail = (data as { detail?: unknown } | undefined)?.detail;
    if (Array.isArray(detail)) {
      const fields = detail as FieldError[];
      throw new ApiError(res.status, fields.map((f) => f.msg).join(" "), fields, code);
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : `Request failed (${res.status}).`, [], code, left === null ? null : Number(left));
  }
  return data as T;
}

export const get = <T,>(path: string, signal?: AbortSignal) => api<T>(path, { signal });
export const post = <T,>(path: string, body?: unknown, headers?: Record<string, string>) =>
  api<T>(path, { method: "POST", body: body ?? {}, headers });
export const put = <T,>(path: string, body: unknown, headers?: Record<string, string>) => api<T>(path, { method: "PUT", body, headers });
export const patch = <T,>(path: string, body: unknown) => api<T>(path, { method: "PATCH", body });

export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}
