import { useId, type ComponentProps, type InputHTMLAttributes, type ReactNode } from "react";
import { AlertTriangle, CircleCheck, CircleX, Info, Inbox, RefreshCw, X, type LucideIcon } from "lucide-react";
import { cn } from "../lib/cn";
import { Button } from "./Button";

const control =
  "w-full rounded-field border border-line-strong bg-surface px-3 text-base text-ink placeholder:text-muted " +
  "transition-colors duration-(--dur-feedback) focus-visible:outline-3 focus-visible:outline-focus " +
  "aria-[invalid=true]:border-red aria-[invalid=true]:bg-red-tint disabled:opacity-60";

type FieldShell = { label: ReactNode; error?: string | null; help?: ReactNode; className?: string; suffix?: ReactNode };

function Shell({ id, label, error, help, className, children }: FieldShell & { id: string; children: ReactNode }) {
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <label htmlFor={id} className="text-sm font-semibold text-ink">
        {label}
      </label>
      {children}
      {help && !error && (
        <p id={`${id}-help`} className="text-xs text-muted">
          {help}
        </p>
      )}
      {error && (
        <p id={`${id}-err`} className="flex items-start gap-1 text-xs font-semibold text-red" role="alert">
          <AlertTriangle size={14} aria-hidden className="mt-0.5 shrink-0" />
          {error}
        </p>
      )}
    </div>
  );
}

export function TextField({ label, error, help, className, suffix, ...rest }: FieldShell & ComponentProps<"input">) {
  const auto = useId();
  const id = rest.id ?? auto;
  return (
    <Shell id={id} label={label} error={error} help={help} className={className}>
      <div className="relative">
        <input
          id={id}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-err` : help ? `${id}-help` : undefined}
          className={cn(control, "min-h-10", suffix ? "pr-14" : "", rest.type === "number" && "tabular")}
          {...rest}
        />
        {suffix && <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm text-muted">{suffix}</span>}
      </div>
    </Shell>
  );
}

export function TextArea({ label, error, help, className, ...rest }: FieldShell & ComponentProps<"textarea">) {
  const auto = useId();
  const id = rest.id ?? auto;
  return (
    <Shell id={id} label={label} error={error} help={help} className={className}>
      <textarea
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-err` : help ? `${id}-help` : undefined}
        className={cn(control, "min-h-24 py-2 leading-normal")}
        {...rest}
      />
    </Shell>
  );
}

export function SelectField({ label, error, help, className, children, ...rest }: FieldShell & ComponentProps<"select">) {
  const auto = useId();
  const id = rest.id ?? auto;
  return (
    <Shell id={id} label={label} error={error} help={help} className={className}>
      <select
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-err` : help ? `${id}-help` : undefined}
        className={cn(control, "min-h-10 pr-8")}
        {...rest}
      >
        {children}
      </select>
    </Shell>
  );
}

export function Checkbox({ label, className, ...rest }: { label: ReactNode } & Omit<InputHTMLAttributes<HTMLInputElement>, "type">) {
  const id = useId();
  return (
    <div className={cn("flex items-start gap-2", className)}>
      <input id={rest.id ?? id} type="checkbox" className="mt-0.5 size-5 shrink-0 accent-(--teal)" {...rest} />
      <label htmlFor={rest.id ?? id} className="text-base leading-snug">
        {label}
      </label>
    </div>
  );
}

/** Small rounded label. Tone carries meaning and is always paired with text. */
export type Tone = "neutral" | "teal" | "red" | "green" | "marigold";
const TONE: Record<Tone, string> = {
  neutral: "bg-tint text-ink border-line",
  teal: "bg-tint text-teal border-teal/40",
  red: "bg-red-tint text-red border-red/40",
  green: "bg-green-tint text-green border-green/40",
  marigold: "bg-marigold text-on-marigold border-on-marigold/30",
};
export function Pill({ tone = "neutral", icon: Icon, children, className }: { tone?: Tone; icon?: LucideIcon; children: ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold whitespace-nowrap", TONE[tone], className)}>
      {Icon && <Icon size={13} aria-hidden strokeWidth={2.5} />}
      {children}
    </span>
  );
}

export function Chip({ children, onRemove, removeLabel }: { children: ReactNode; onRemove?: () => void; removeLabel?: string }) {
  return (
    <span className="inline-flex min-h-12 items-center gap-2 rounded-full border border-teal bg-tint pl-4 pr-1 text-k-body font-semibold text-teal">
      {children}
      {onRemove && (
        <button type="button" onClick={onRemove} aria-label={removeLabel} className="inline-flex size-10 items-center justify-center rounded-full hover:bg-surface">
          <X size={22} aria-hidden strokeWidth={2.5} />
        </button>
      )}
    </span>
  );
}

/** Flat bordered panel (elevation 0). */
export function Panel({ title, actions, children, className, id }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; id?: string }) {
  return (
    <section id={id} className={cn("rounded-panel border border-line bg-surface", className)} aria-labelledby={title && id ? `${id}-title` : undefined}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
          {title && (
            <h2 id={id ? `${id}-title` : undefined} className="text-md font-semibold">
              {title}
            </h2>
          )}
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("animate-pulse rounded-field bg-tint", className)} />;
}

export function EmptyState({ title, children, icon: Icon = Inbox, action }: { title: string; children?: ReactNode; icon?: LucideIcon; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-2 rounded-panel border border-dashed border-line-strong px-5 py-6">
      <Icon size={22} aria-hidden className="text-muted" />
      <p className="text-md font-semibold">{title}</p>
      {children && <div className="max-w-prose text-base text-muted">{children}</div>}
      {action}
    </div>
  );
}

export function ErrorState({ title, message, onRetry, retryLabel = "Try again" }: { title: string; message: string; onRetry?: () => void; retryLabel?: string }) {
  return (
    <div role="alert" className="flex flex-col items-start gap-2 rounded-panel border border-red/50 bg-red-tint px-5 py-4">
      <p className="flex items-center gap-2 text-md font-semibold text-red">
        <CircleX size={20} aria-hidden /> {title}
      </p>
      <p className="max-w-prose text-base">{message}</p>
      {onRetry && (
        <Button size="sm" icon={RefreshCw} onClick={onRetry}>
          {retryLabel}
        </Button>
      )}
    </div>
  );
}

export type NoticeTone = "info" | "ok" | "warn" | "stop";
const NOTICE: Record<NoticeTone, { cls: string; icon: LucideIcon }> = {
  info: { cls: "border-line bg-tint text-ink", icon: Info },
  ok: { cls: "border-green/50 bg-green-tint text-ink", icon: CircleCheck },
  warn: { cls: "border-on-marigold/30 bg-marigold-tint text-ink", icon: AlertTriangle },
  stop: { cls: "border-red/50 bg-red-tint text-ink", icon: CircleX },
};
export function Notice({ tone = "info", title, children, className }: { tone?: NoticeTone; title?: ReactNode; children?: ReactNode; className?: string }) {
  const { cls, icon: Icon } = NOTICE[tone];
  const iconCls = tone === "ok" ? "text-green" : tone === "stop" ? "text-red" : tone === "warn" ? "text-on-marigold" : "text-teal";
  return (
    <div className={cn("flex gap-3 rounded-panel border px-4 py-3", cls, className)}>
      <Icon size={20} aria-hidden className={cn("mt-0.5 shrink-0", iconCls)} />
      <div className="min-w-0 text-base">
        {title && <p className="font-semibold">{title}</p>}
        {children}
      </div>
    </div>
  );
}

/** "Prototype data, not clinically verified": on every dosing view, always visible. */
export function PrototypeBanner({ text = "Prototype data, not clinically verified", extra }: { text?: string; extra?: string }) {
  return (
    <p className="flex items-center gap-2 rounded-field border border-on-marigold/30 bg-marigold-tint px-3 py-2 text-sm font-semibold">
      <AlertTriangle size={16} aria-hidden className="shrink-0" />
      {text}
      {extra && <span className="font-normal text-muted">{extra}</span>}
    </p>
  );
}

/** Red DEMO bar, shown only when the engine result carries `demo`. */
export function DemoBar({ text }: { text: string }) {
  return (
    <p role="status" className="rounded-field bg-red-fill px-3 py-2 text-center text-sm font-bold text-on-red">
      {text}
    </p>
  );
}
