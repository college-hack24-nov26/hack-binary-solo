import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { MonitorSmartphone, Stethoscope, Users, type LucideIcon } from "lucide-react";
import { get, type SystemConfig } from "./api/client";

const SURFACES: { to: string; title: string; who: string; icon: LucideIcon }[] = [
  { to: "/kiosk", title: "Patient kiosk", who: "For the tablet in the waiting area. Bookmark this address on the tablet and pin the screen.", icon: MonitorSmartphone },
  { to: "/staff", title: "Staff desk", who: "Live board of today's patients, red flags, help requests, vitals and scans.", icon: Users },
  { to: "/doctor", title: "Doctor workstation", who: "Patient summary, scan confirmation, notes, dosage check and the audit log.", icon: Stethoscope },
];

/** Small chooser for the demo laptop. A tablet never sees this: it is bookmarked straight to /kiosk. */
export function Chooser({ notFound }: { notFound?: boolean }) {
  const cfg = useQuery({ queryKey: ["config"], queryFn: () => get<SystemConfig>("/api/system/config") });
  return (
    <main className="mx-auto flex min-h-dvh max-w-3xl flex-col justify-center gap-8 px-5 py-10">
      <header>
        <p className="text-sm font-semibold text-teal">MediKiosk OPD · runs on this computer, no internet</p>
        <h1 className="mt-1 text-2xl font-bold">Open a screen</h1>
        {notFound && <p className="mt-2 text-base text-muted">That address does not exist. Pick one of the screens below.</p>}
      </header>
      <ul className="grid gap-3">
        {SURFACES.map((s) => (
          <li key={s.to}>
            <Link to={s.to} className="flex items-start gap-4 rounded-panel border border-line bg-surface px-5 py-4 hover:border-teal hover:bg-tint">
              <s.icon size={28} aria-hidden className="mt-0.5 shrink-0 text-teal" />
              <span>
                <span className="block text-lg font-semibold">{s.title}</span>
                <span className="block text-base text-muted">{s.who}</span>
                <span className="mt-1 block font-mono text-xs text-muted">{s.to}</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
      {cfg.data && (
        <p className="text-sm text-muted">
          {cfg.data.demoMode ? "Demo mode is on: synthetic patients only. " : ""}
          {cfg.data.formularyLoaded ? "" : "Dosing is unavailable: the formulary did not load. "}
          {cfg.data.ocrAvailable ? "Scanning is available." : "Scanning is unavailable until the local model server runs."}
          {(cfg.data.demoMode || import.meta.env.DEV) && (
            <>
              {" "}
              <Link to="/gallery" className="font-semibold text-teal underline">
                Component gallery
              </Link>
            </>
          )}
        </p>
      )}
    </main>
  );
}
