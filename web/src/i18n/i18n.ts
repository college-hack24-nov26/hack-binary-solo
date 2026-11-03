import kiosk from "./kiosk.json";

export type Lang = "en" | "hi" | "mr";
export const LANGS: Lang[] = ["en", "hi", "mr"];
export const LANG_NAMES: Record<Lang, string> = { en: "English", hi: "हिन्दी", mr: "मराठी" };
export const LANG_TAG: Record<Lang, string> = { en: "en-IN", hi: "hi-IN", mr: "mr-IN" };

type Strings = typeof kiosk.strings;
export type Key = keyof Strings;

/** Kiosk chrome text in the patient's language, English fallback. `{name}` placeholders are filled from vars. */
export function t(key: Key, lang: Lang, vars?: Record<string, string | number>): string {
  const entry = kiosk.strings[key] as Record<Lang, string>;
  let s = entry[lang] || entry.en;
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(String(v));
  return s;
}

/** Western digits in every script: OPD tokens, rooms and doses are read and compared across staff and patients. */
export function num(n: number | string): string {
  return String(n);
}
