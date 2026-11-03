import { Siren, TriangleAlert } from "lucide-react";
import type { RedFlag } from "../api/client";
import { cn } from "../lib/cn";

/** One fired red-flag rule for staff and doctors: icon + severity word + staff message + draft label + triggering answers. */
export function RedFlagRow({ flag, token, attention, compact, action }: { flag: RedFlag; token?: string; attention?: boolean; compact?: boolean; action?: React.ReactNode }) {
  const urgent = flag.severity === "urgent";
  return (
    <div
      className={cn(
        "flex gap-3 rounded-panel border border-l-4 px-4 py-3",
        urgent ? "border-red/50 border-l-red bg-red-tint" : "border-on-marigold/30 border-l-marigold bg-marigold-tint",
        attention && "animate-attention",
      )}
      data-testid="redflag-row"
    >
      {urgent ? <Siren size={22} aria-hidden className="mt-0.5 shrink-0 text-red" /> : <TriangleAlert size={22} aria-hidden className="mt-0.5 shrink-0" />}
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-baseline gap-x-2">
          <span className={cn("font-bold", urgent ? "text-red" : "")}>{urgent ? "Urgent" : "Soon"}</span>
          {token && <span className="font-semibold tabular">{token}</span>}
          <span className="font-semibold">{flag.staffMessage}</span>
        </p>
        <p className="text-xs text-muted">
          {flag.draft ? <span className="font-semibold">{flag.label}</span> : flag.label} · rule {flag.ruleId}
        </p>
        {!compact && flag.triggeredBy.length > 0 && (
          <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-sm">
            {flag.triggeredBy.map((t) => (
              <li key={t.nodeId}>
                <span className="text-muted">{/[?:]$/.test(t.label) ? t.label : `${t.label}:`}</span> <span className="font-semibold">{t.answer}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      {action}
    </div>
  );
}
