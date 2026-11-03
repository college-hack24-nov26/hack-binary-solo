import { useEffect, useId, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ShieldCheck, TriangleAlert, Wifi, WifiOff } from "lucide-react";
import { get, type OfflineStatus } from "../api/client";
import { cn } from "../lib/cn";

/** "Offline: no internet used" pill with a live dot; opens to the network details the server reports. Never claims more. */
export function OfflineBadge() {
  const q = useQuery({
    queryKey: ["offline-status"],
    queryFn: () => get<OfflineStatus>("/api/system/offline-status"),
    refetchInterval: (query) => ((query.state.data?.probe.intervalS ?? 30) * 1000),
  });
  const [open, setOpen] = useState(false);
  const id = useId();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);
  const s = q.data;
  const level = s?.level ?? "pending";
  const net = s?.internet as { reachable?: boolean; took_s?: number } | null | undefined;
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "inline-flex min-h-8 items-center gap-2 rounded-full border px-3 text-xs font-semibold",
          level === "warn" ? "border-on-marigold/30 bg-marigold-tint" : "border-green/40 bg-green-tint",
        )}
      >
        <span className="relative flex size-2" aria-hidden>
          <span className={cn("absolute inline-flex size-full rounded-full opacity-60 motion-safe:animate-ping", level === "warn" ? "bg-marigold" : "bg-green")} />
          <span className={cn("relative inline-flex size-2 rounded-full", level === "warn" ? "bg-on-marigold" : "bg-green")} />
        </span>
        <span>Offline: no internet used</span>
        {level === "warn" && <span className="hidden font-normal sm:inline">· internet reachable, not used</span>}
        <ChevronDown size={14} aria-hidden />
      </button>
      {open && (
        <div id={id} role="dialog" aria-label="Network details" className="absolute right-0 top-10 z-40 w-[min(22rem,calc(100vw-2rem))] rounded-panel border border-line bg-surface p-4 text-sm shadow-(--shadow-overlay)">
          {!s ? (
            <p>Checking the network…</p>
          ) : (
            <dl className="grid gap-3">
              <div>
                <dt className="font-semibold">What this app talks to</dt>
                <dd className="text-muted">
                  Only {s.localModel.host}:{s.localModel.port} (local model server on this computer):{" "}
                  <span className={s.localModel.reachable ? "text-green" : "text-ink"}>{s.localModel.reachable ? "reachable" : `not running (${s.localModel.error ?? "no answer"})`}</span>
                </dd>
              </div>
              <div>
                <dt className="font-semibold">Where data lives</dt>
                {s.services.map((x) => (
                  <dd key={x.name} className="break-all text-muted">
                    {x.name}: {x.target}
                  </dd>
                ))}
              </div>
              <div>
                <dt className="flex items-center gap-1 font-semibold">
                  {s.strict ? <ShieldCheck size={15} aria-hidden /> : net?.reachable ? <Wifi size={15} aria-hidden /> : net ? <WifiOff size={15} aria-hidden /> : <TriangleAlert size={15} aria-hidden />}
                  Internet
                </dt>
                <dd className="text-muted">
                  {s.strict
                    ? "Strict mode is on: any connection outside this computer is blocked and logged. The public check is not run."
                    : !net
                      ? "Check not finished yet."
                      : `${net.reachable ? "Reachable (not used by this app)" : "Unreachable"}. Checked by one connection to ${s.probe.host}:${s.probe.port} every ${s.probe.intervalS} s; the app itself never uses it.`}
                </dd>
              </div>
            </dl>
          )}
        </div>
      )}
    </div>
  );
}
