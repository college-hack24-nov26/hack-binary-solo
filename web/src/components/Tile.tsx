import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Check } from "lucide-react";
import { cn } from "../lib/cn";

/** Prefers-reduced-motion users get no vibration either. */
export function tapFeedback() {
  try {
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) navigator.vibrate?.(10);
  } catch {
    /* not supported */
  }
}

/**
 * Kiosk answer tile: 96 px tall key with a pressable bottom edge. Selected shows a check icon and the word in the patient's
 * language, never colour alone.
 */
export function Tile({ selected, selectedLabel, children, sub, className, onClick, ...rest }:
  Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> & { selected?: boolean; selectedLabel: string; children: ReactNode; sub?: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={(e) => {
        tapFeedback();
        onClick?.(e);
      }}
      className={cn(
        "group relative flex min-h-24 w-full items-center gap-4 rounded-tile border-2 px-5 py-4 text-left",
        "border-b-[5px] transition-[transform,background-color,border-color] duration-(--dur-feedback) ease-std",
        "active:translate-y-[3px] active:border-b-2",
        selected ? "border-teal border-b-teal-press bg-tint" : "border-line-strong border-b-line-strong bg-surface hover:bg-tint/60",
        "disabled:opacity-50",
        className,
      )}
      {...rest}
    >
      <span className="min-w-0 flex-1">
        <span className={cn("block text-k-tile font-semibold", selected ? "text-teal" : "text-ink")}>{children}</span>
        {sub && <span className="mt-0.5 block text-k-body text-muted">{sub}</span>}
      </span>
      <span
        className={cn(
          "flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1 text-k-body font-semibold transition-opacity duration-(--dur-feedback)",
          selected ? "bg-teal text-on-teal opacity-100" : "opacity-0",
        )}
        aria-hidden={!selected}
      >
        <Check size={22} strokeWidth={3} aria-hidden />
        {selected ? selectedLabel : ""}
      </span>
    </button>
  );
}
