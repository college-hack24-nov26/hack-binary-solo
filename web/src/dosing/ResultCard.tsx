import type { ReactNode } from "react";
import { ArrowLeftRight, Ban, ChevronRight, CircleCheck, ClipboardList, OctagonX, TriangleAlert, type LucideIcon } from "lucide-react";
import type { Card } from "../api/client";
import { DemoBar } from "../components/ui";
import { cn } from "../lib/cn";
import { DoseRuler } from "./DoseRuler";
import { show, type DoseResult, type Plan, type Status } from "./types";

const HEAD: Record<Status, { icon: LucideIcon; cls: string; iconCls: string }> = {
  ok: { icon: CircleCheck, cls: "border-green/50 bg-green-tint", iconCls: "text-green" },
  needs_input: { icon: ClipboardList, cls: "border-teal/40 bg-tint", iconCls: "text-teal" },
  blocked: { icon: OctagonX, cls: "border-red/60 bg-red-tint", iconCls: "text-red" },
  refused: { icon: Ban, cls: "border-red/60 bg-red-tint", iconCls: "text-red" },
};

export function Disclosure({ summary, children, open, testId }: { summary: ReactNode; children: ReactNode; open?: boolean; testId?: string }) {
  return (
    <details className="group rounded-field border border-line" open={open} data-testid={testId}>
      <summary className="flex min-h-10 cursor-pointer list-none items-center gap-2 px-3 text-sm font-semibold [&::-webkit-details-marker]:hidden">
        <ChevronRight size={16} aria-hidden className="transition-transform duration-(--dur-feedback) group-open:rotate-90" />
        {summary}
      </summary>
      <div className="border-t border-line px-3 py-3 text-sm">{children}</div>
    </details>
  );
}

function planText(p: Plan): string | null {
  if (!p) return null;
  if (typeof p === "string") return p;
  return [p.start && `Start ${p.start}`, p.step && `then ${p.step}`, p.max_per_day_mg !== undefined && `maximum ${show(p.max_per_day_mg)} mg a day`, p.note]
    .filter(Boolean)
    .join("; ");
}

/** The dose itself. Rendered only for status "ok" (and only from engine fields). */
export function DoseFigure({ r }: { r: DoseResult }) {
  if (r.status !== "ok" || r.dose_mg === null || r.dose_mg === undefined) return null;
  const qty = r.volume_ml ? `${show(r.volume_ml)} mL of ${r.product}` : r.units ? `${show(r.units)} × ${r.product}` : r.product;
  const freq = r.interval_h ? `every ${show(r.interval_h)} h` : r.doses_per_day ? `${show(r.doses_per_day)} doses a day` : null;
  return (
    <div data-testid="dose-figure">
      <p className="text-dose font-bold tabular">{show(r.dose_mg)} mg</p>
      <p className="text-lg">
        = <span className="font-semibold tabular">{qty}</span>
        {freq && <span className="text-muted">, {freq}</span>}
      </p>
      {r.daily_total_mg !== null && (
        <p className="mt-1 text-sm text-muted tabular">
          Daily total {show(r.daily_total_mg)} mg{r.daily_max_mg !== null ? ` · daily maximum ${show(r.daily_max_mg)} mg` : ""}
        </p>
      )}
    </div>
  );
}

/** One bordered group per kind, items divided by hairlines (not a stack of identical boxes). */
function ItemList({ title, items, icon: Icon, tone }: { title: string; items: string[]; icon: LucideIcon; tone: "red" | "marigold" | "neutral" }) {
  const edge = tone === "red" ? "border-l-red" : tone === "marigold" ? "border-l-marigold" : "border-l-line-strong";
  const ic = tone === "red" ? "text-red" : tone === "marigold" ? "text-on-marigold dark:text-marigold" : "text-muted";
  return (
    <section className={cn("rounded-panel border border-l-4 border-line bg-surface", edge)} aria-label={title}>
      <h4 className="px-4 pt-3 text-sm font-semibold">{title}</h4>
      <ul className="divide-y divide-line px-4 pb-1">
        {items.map((t, i) => (
          <li key={i} className="flex gap-2 py-2 text-sm">
            <Icon size={16} aria-hidden className={cn("mt-0.5 shrink-0", ic)} />
            <span>{t}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

type Slots = { missing?: ReactNode; override?: ReactNode; confirm?: ReactNode; alternatives?: ReactNode };

/**
 * Display of one evaluation: header per status, reason, responsible rule or input, sources for blocks, overrides, then the dose
 * (ok only). blocked/refused hide every dose figure, range, regimen, plan, duration and step; needs_input hides them too
 * (no dose number is shown unless status is ok).
 */
export function ResultCard({ result: r, card, slots = {} }: { result: DoseResult; card: Card; slots?: Slots }) {
  const status = r.status;
  const h = HEAD[status];
  const ok = status === "ok";
  const plan = ok ? planText(r.plan) : null;
  return (
    <article className="flex flex-col gap-4" aria-labelledby="result-header" data-testid="result-card" data-status={status}>
      {r.demo && r.demo_banner && <DemoBar text={r.demo_banner} />}
      <div className={cn("rounded-panel border-l-4 border px-4 py-4", h.cls)}>
        <h3 id="result-header" className="flex items-center gap-2 text-2xl font-bold">
          <h.icon size={28} aria-hidden className={h.iconCls} strokeWidth={2.25} />
          {card.header}
        </h3>
        <p className="mt-2 text-md">{card.reason}</p>
        <p className="mt-1 text-sm text-muted">{card.responsible}</p>
        {card.sources.length > 0 && (
          <div className="mt-3">
            <p className="text-sm font-semibold">Source</p>
            <ul className="mt-1 flex flex-col gap-1 text-sm">
              {card.sources.map((s, i) => (
                <li key={i}>
                  {s.id ? <span className="font-semibold">{String(s.id)} </span> : null}
                  {String(s.name)}
                  {s.url ? <span className="block break-all text-xs text-muted">{String(s.url)}</span> : null}
                </li>
              ))}
            </ul>
          </div>
        )}
        {card.overrides.map((o, i) => (
          <p key={i} className="mt-3 flex flex-wrap items-baseline gap-x-2 text-sm" data-testid="override-recorded">
            <span className="font-bold text-red">Override recorded</span>
            <span>{String(o.category_label)}</span>
            <span>“{String(o.reason)}”</span>
            <span className="text-muted">{String(o.doctor_id)}</span>
          </p>
        ))}
      </div>

      {slots.missing}
      {slots.override}

      {ok && (
        <div className="grid gap-6 rounded-panel border border-line bg-surface p-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
          <div className="flex flex-col gap-2">
            <DoseFigure r={r} />
            {plan && (
              <p className="text-base">
                <span className="font-semibold">Titration plan: </span>
                {plan}
              </p>
            )}
            {r.text_regimen && (
              <p className="text-base">
                <span className="font-semibold">Regimen (formulary text, not computed): </span>
                {r.text_regimen}
              </p>
            )}
            {r.duration && (
              <p className="text-base">
                <span className="font-semibold">Duration: </span>
                {r.duration}
              </p>
            )}
            {!r.final && r.pending_confirmations.length > 0 && (
              <p className="text-sm font-semibold text-on-marigold">
                <span className="rounded-field bg-marigold px-2 py-0.5">Provisional</span> confirm {r.pending_confirmations.join(", ")}
              </p>
            )}
          </div>
          <DoseRuler result={r} />
        </div>
      )}

      {slots.alternatives}

      <Disclosure summary={`Calculation steps${ok ? ` (${r.calculation_steps.length})` : ""}`} testId="steps">
        {ok ? (
          <ol className="flex list-decimal flex-col gap-1.5 pl-5 tabular">
            {r.calculation_steps.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
        ) : (
          <p className="text-muted">
            {status === "needs_input"
              ? "Shown once the missing items are filled in: no dose figure appears before then."
              : "Hidden until an override is recorded: no dose figure is shown for a blocked or refused case."}
          </p>
        )}
      </Disclosure>

      {r.blocks.length > 0 && (
        <ItemList title={`Safety rules that fired (${r.blocks.length})`} tone="red" icon={OctagonX} items={r.blocks.map((b) => b.text)} />
      )}
      {r.interactions.length > 0 && (
        <ItemList
          title={`Interactions (${r.interactions.length})`}
          tone="marigold"
          icon={ArrowLeftRight}
          items={r.interactions.map((x) => {
            const scan = x.origins?.find((o) => o.source === "ocr_doctor_confirmed");
            return scan ? `${x.text} (from scanned prescription${scan.scan_date ? `, ${scan.scan_date}` : ""})` : x.text;
          })}
        />
      )}
      {r.warnings.length > 0 && <ItemList title={`Warnings (${r.warnings.length})`} tone="neutral" icon={TriangleAlert} items={r.warnings.map((w) => w.text)} />}

      {r.label_warnings.length > 0 && (
        <Disclosure summary={`Label warnings (${r.label_warnings.length})`}>
          <ul className="flex flex-col gap-1">
            {r.label_warnings.map((w, i) => (
              <li key={i}>{w.text}</li>
            ))}
          </ul>
        </Disclosure>
      )}
      <Disclosure summary={`Sources (${r.sources.length})`}>
        <ul className="flex flex-col gap-2">
          {r.sources.map((s, i) => (
            <li key={i}>
              <span className="font-semibold">{s.id ?? "-"}</span> {s.name} <span className="text-muted">[{s.status}]</span>
              {s.section && <span className="block text-xs text-muted">{s.section}</span>}
              {s.url && <span className="block break-all text-xs text-muted">{s.url}</span>}
            </li>
          ))}
        </ul>
      </Disclosure>

      {slots.confirm}
    </article>
  );
}
