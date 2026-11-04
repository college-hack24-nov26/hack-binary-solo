// Format checks for the kiosk identity step. Format only: nothing is verified against any registry (the kiosk is offline).
// The server normalises and validates again; these helpers drive the live feedback and the number pad.
export type IdKind = "mobile" | "abha";
export type Feedback = { state: "empty" | "partial" | "ok" | "bad"; remaining: number; reason: "mobile" | "abha" | null };

export const LENGTH: Record<IdKind, number> = { mobile: 10, abha: 14 };
/** Visual groups of digits: 5+5 for a mobile number, 2-4-4-4 for ABHA (the printed 91-xxxx-xxxx-xxxx form). */
export const GROUPS: Record<IdKind, number[]> = { mobile: [5, 5], abha: [2, 4, 4, 4] };

/** Keep digits only, accepting pasted or typed 91-1234-5678-9012, "+91 98765 43210" and so on. */
export function digitsOf(raw: string): string {
  return raw.replace(/\D/g, "");
}

/** A mobile entry may arrive with a +91 / 91 / 0 prefix; strip it so 10 digits remain. */
export function stripMobilePrefix(d: string): string {
  if (d.length === 12 && d.startsWith("91")) return d.slice(2);
  if (d.length === 11 && d.startsWith("0")) return d.slice(1);
  return d;
}

export function pushDigit(kind: IdKind, current: string, digit: string): string {
  if (!/^\d$/.test(digit) || current.length >= LENGTH[kind]) return current;
  if (kind === "mobile" && current.length === 0 && Number(digit) < 6) return current;     // an Indian mobile number starts 6-9
  return current + digit;
}

export function popDigit(current: string): string {
  return current.slice(0, -1);
}

export function checkIdentifier(kind: IdKind, digits: string): Feedback {
  const n = LENGTH[kind];
  if (digits.length === 0) return { state: "empty", remaining: n, reason: null };
  if (kind === "mobile" && !/^[6-9]/.test(digits)) return { state: "bad", remaining: n - digits.length, reason: "mobile" };
  if (digits.length < n) return { state: "partial", remaining: n - digits.length, reason: null };
  if (digits.length > n) return { state: "bad", remaining: 0, reason: kind };
  return { state: "ok", remaining: 0, reason: null };
}

/** Split `digits` into the display groups, padding with empty slots so the boxes never jump around. */
export function slots(kind: IdKind, digits: string): string[][] {
  let i = 0;
  return GROUPS[kind].map((g) => Array.from({ length: g }, () => digits[i++] ?? ""));
}

// ---- PIN
export const PIN_LENGTH = 4;
export function pushPin(pin: string, digit: string): string {
  return /^\d$/.test(digit) && pin.length < PIN_LENGTH ? pin + digit : pin;
}
export const pinComplete = (pin: string) => /^\d{4}$/.test(pin);
export const pinsMatch = (a: string, b: string) => pinComplete(a) && a === b;

/** The new-patient PIN flow: choose, then type it again. A mismatch goes back to "choose" with a message. */
export type PinPhase = { phase: "choose" | "again"; first: string; entry: string; mismatch: boolean };
export const PIN_START: PinPhase = { phase: "choose", first: "", entry: "", mismatch: false };

export function pinStep(s: PinPhase, action: { digit: string } | { delete: true }): PinPhase {
  if ("delete" in action) return { ...s, entry: s.entry.slice(0, -1), mismatch: false };
  const entry = pushPin(s.entry, action.digit);
  if (!pinComplete(entry)) return { ...s, entry, mismatch: false };
  if (s.phase === "choose") return { phase: "again", first: entry, entry: "", mismatch: false };
  return pinsMatch(s.first, entry) ? { ...s, entry } : { ...PIN_START, mismatch: true };
}
export const pinConfirmed = (s: PinPhase) => s.phase === "again" && pinsMatch(s.first, s.entry);
