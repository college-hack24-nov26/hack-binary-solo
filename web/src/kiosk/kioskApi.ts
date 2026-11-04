import { api, type IdentityOut, type KioskCreated, type KioskScreen, type ReviewItem, type ScanOut, type TokenSlip } from "../api/client";
import type { Lang } from "../i18n/i18n";

// The tablet keeps only {token, kioskKey, lang} in sessionStorage; it is cleared on every reset.
const KEY = "mk.kiosk";
export type Saved = { token: string; kioskKey: string; lang: Lang; identity?: string; masked?: string; scansAllowed?: boolean };

/** A random id for this tablet, kept in localStorage: the server rate-limits identity attempts per device. */
export function deviceId(): string {
  try {
    let d = localStorage.getItem("mk.device");
    if (!d) {
      d = crypto.randomUUID();
      localStorage.setItem("mk.device", d);
    }
    return d;
  } catch {
    return "unknown";
  }
}
const dev = () => ({ "X-Kiosk-Device": deviceId() });

export type IdKind = "mobile" | "abha";
export const identityApi = {
  identify: (type: IdKind, identifier: string) => api<{ exists: boolean; masked: string }>("/api/kiosk/identify", { method: "POST", body: { type, identifier }, headers: dev() }),
  register: (type: IdKind, identifier: string, pin: string, language: Lang) =>
    api<IdentityOut>("/api/kiosk/register", { method: "POST", body: { type, identifier, pin, consent: { agreed: true, language } }, headers: dev() }),
  login: (type: IdKind, identifier: string, pin: string) => api<IdentityOut>("/api/kiosk/login", { method: "POST", body: { type, identifier, pin }, headers: dev() }),
  walkIn: (language: Lang) => api<IdentityOut>("/api/kiosk/walk-in", { method: "POST", body: { language }, headers: dev() }),
};

export function loadSaved(): Saved | null {
  try {
    const s = sessionStorage.getItem(KEY);
    return s ? (JSON.parse(s) as Saved) : null;
  } catch {
    return null;
  }
}
export function save(s: Saved) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* private mode: the session still works until the page reloads */
  }
}
export function clearSaved() {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}

export function kioskClient(s: Saved) {
  const base = `/api/kiosk/sessions/${s.token}`;
  const h = { "X-Kiosk-Key": s.kioskKey };
  const hi = { ...h, "X-Kiosk-Identity": s.identity ?? "" };
  const sc = `${base}/scans`;
  return {
    bind: (identity: string) => api<KioskScreen>(`${base}/bind`, { method: "POST", body: {}, headers: { ...h, "X-Kiosk-Identity": identity } }),
    end: () => api<void>(`${base}/end`, { method: "POST", body: {}, headers: hi }),
    scans: {
      upload: (blob: Blob) => {
        const fd = new FormData();
        fd.set("image", blob, "paper.jpg");
        return api<ScanOut>(sc, { form: fd, headers: hi });
      },
      get: (id: string) => api<ScanOut>(`${sc}/${id}`, { headers: hi }),
      correct: (id: string, body: Record<string, unknown>) => api<ScanOut>(`${sc}/${id}`, { method: "PATCH", body, headers: hi }),
      confirm: (id: string) => api<ScanOut>(`${sc}/${id}/confirm`, { method: "POST", body: {}, headers: hi }),
      remove: (id: string) => api<void>(`${sc}/${id}`, { method: "DELETE", headers: hi }),
      /** The thumbnail needs our headers, so it is fetched and shown from a blob URL (revoke it when done). */
      image: async (id: string) => {
        const r = await fetch(`${sc}/${id}/image`, { headers: hi });
        return r.ok ? URL.createObjectURL(await r.blob()) : null;
      },
    },
    screen: (node?: string) => api<KioskScreen>(`${base}${node ? `?node=${encodeURIComponent(node)}` : ""}`, { headers: h }),
    consent: (choice: "agree" | "decline") => api<KioskScreen>(`${base}/consent`, { method: "POST", body: { choice }, headers: h }),
    answer: (nodeId: string, value: unknown) => api<KioskScreen>(`${base}/answers`, { method: "POST", body: { nodeId, value }, headers: h }),
    bodymap: (b: { nodeId: string; regions?: string[]; view?: "front" | "back"; inputMode?: "map" | "list"; special?: string }) =>
      api<KioskScreen>(`${base}/bodymap`, { method: "POST", body: b, headers: h }),
    skip: (nodeId: string) => api<KioskScreen>(`${base}/skip`, { method: "POST", body: { nodeId }, headers: h }),
    back: (nodeId: string | null) => api<KioskScreen>(`${base}/back`, { method: "POST", body: { nodeId }, headers: h }),
    language: (language: Lang, node?: string) =>
      api<KioskScreen>(`${base}/language${node ? `?node=${encodeURIComponent(node)}` : ""}`, { method: "PUT", body: { language }, headers: h }),
    review: () => api<{ items: ReviewItem[] }>(`${base}/review`, { headers: h }),
    doctor: (doctorId: string | null) => api<KioskScreen>(`${base}/doctor`, { method: "POST", body: { doctorId }, headers: h }),
    finish: () => api<TokenSlip>(`${base}/finish`, { method: "POST", body: {}, headers: h }),
    help: () => api<void>(`${base}/help`, { method: "POST", body: {}, headers: h }),
  };
}

export async function createSession(lang: Lang): Promise<KioskCreated> {
  return api<KioskCreated>("/api/kiosk/sessions", { method: "POST", body: { language: lang } });
}
