import { api, type KioskCreated, type KioskScreen, type ReviewItem, type TokenSlip } from "../api/client";
import type { Lang } from "../i18n/i18n";

// The tablet keeps only {token, kioskKey, lang} in sessionStorage; it is cleared on every reset.
const KEY = "mk.kiosk";
export type Saved = { token: string; kioskKey: string; lang: Lang };

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
  return {
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
