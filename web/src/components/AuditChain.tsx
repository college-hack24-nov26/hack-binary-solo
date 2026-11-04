import { Link2, ShieldAlert, ShieldCheck } from "lucide-react";
import { cn } from "../lib/cn";

/** "Chain verified" seal (icon + text) or red "Chain broken" naming the first bad entry. Never offers a fix. */
export function ChainSeal({ ok, entries, firstBad }: { ok: boolean | undefined; entries?: number; firstBad?: number | null }) {
  if (ok === undefined)
    return (
      <span className="inline-flex min-h-10 items-center gap-2 rounded-full border border-line px-4 text-sm text-muted" aria-live="polite">
        Checking the chain…
      </span>
    );
  return (
    <span
      role="status"
      data-testid="chain-seal"
      data-ok={ok}
      className={cn(
        "inline-flex min-h-10 items-center gap-2 rounded-full border-2 px-4 text-sm font-bold",
        ok ? "border-green bg-green-tint text-green" : "border-red bg-red-tint text-red",
      )}
    >
      {ok ? <ShieldCheck size={20} aria-hidden /> : <ShieldAlert size={20} aria-hidden />}
      {ok ? "Chain verified" : "Chain broken"}
      <span className="font-normal text-ink tabular">
        {ok
          ? `${entries ?? 0} entries, none changed, removed or reordered`
          : `first bad entry is line ${(firstBad ?? 0) + 1}; the log was edited after it was written`}
      </span>
    </span>
  );
}

/** Short hash link: this entry's prefix, linked to the previous entry's prefix. */
export function HashLink({ hash, prev, bad }: { hash?: string | null; prev?: string | null; bad?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-1 font-mono text-xs tabular", bad ? "font-bold text-red" : "text-muted")} title={hash ?? ""}>
      <span className={cn("rounded-sm px-1", bad ? "bg-red-tint" : "bg-tint text-ink")}>{(hash ?? "").slice(0, 6)}</span>
      <Link2 size={12} aria-label="linked to" />
      <span>{(prev ?? "").slice(0, 6)}</span>
    </span>
  );
}
