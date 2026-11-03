import { useCallback, useEffect, useSyncExternalStore } from "react";

export type ThemePref = "light" | "dark" | "system";
const KEY = "mk.theme";
const listeners = new Set<() => void>();

function read(): ThemePref {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

export function applyTheme(pref: ThemePref = read()) {
  const dark = pref === "dark" || (pref === "system" && window.matchMedia?.("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", Boolean(dark));
}

/** Light / dark / system for staff and doctor (the kiosk is always light). index.html applies it before first paint. */
export function useTheme(): [ThemePref, (p: ThemePref) => void] {
  const pref = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    read,
    () => "system" as ThemePref,
  );
  const set = useCallback((p: ThemePref) => {
    try {
      localStorage.setItem(KEY, p);
    } catch {
      /* private mode: theme still applies for this page */
    }
    applyTheme(p);
    listeners.forEach((l) => l());
  }, []);
  useEffect(() => {
    applyTheme(pref);
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    const on = () => read() === "system" && applyTheme("system");
    mq?.addEventListener("change", on);
    return () => {
      mq?.removeEventListener("change", on);
    };
  }, [pref]);
  return [pref, set];
}
