import { useEffect, useRef, useState, type ButtonHTMLAttributes, type ComponentProps, type ReactNode } from "react";
import { Check, Loader2, type LucideIcon } from "lucide-react";
import { cn } from "../lib/cn";

export type Variant = "primary" | "secondary" | "ghost" | "danger" | "danger-outline" | "success";
export type Size = "sm" | "md" | "kiosk";

type Base = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> & {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: LucideIcon;
  iconRight?: LucideIcon;
  block?: boolean;
  children: ReactNode;
};

const VARIANT: Record<Variant, string> = {
  primary: "bg-teal text-on-teal border-teal hover:bg-teal-press active:bg-teal-press",
  secondary: "bg-surface text-ink border-line-strong hover:bg-tint active:bg-tint",
  ghost: "bg-transparent text-teal border-transparent hover:bg-tint active:bg-tint",
  danger: "bg-red-fill text-on-red border-red-fill hover:brightness-95 active:brightness-90",
  "danger-outline": "bg-surface text-red border-red hover:bg-red-tint active:bg-red-tint",
  success: "bg-green text-on-green border-green",
};

const SIZE: Record<Size, string> = {
  sm: "min-h-8 px-3 text-sm gap-1.5 rounded-field",
  md: "min-h-10 px-4 text-base gap-2 rounded-field",
  kiosk: "min-h-16 px-6 text-k-tile gap-3 rounded-tile",
};
const ICON: Record<Size, number> = { sm: 16, md: 18, kiosk: 28 };

const ICON_ONLY: Record<Size, string> = { sm: "size-8 rounded-field", md: "size-10 rounded-field", kiosk: "size-16 rounded-tile" };

export function buttonClass(variant: Variant = "secondary", size: Size = "md", block = false, iconOnly = false) {
  return cn(
    "relative inline-flex select-none items-center justify-center border font-semibold whitespace-normal text-center",
    "transition-[background-color,transform,filter] duration-(--dur-feedback) ease-std active:translate-y-px",
    "disabled:cursor-not-allowed disabled:opacity-50 disabled:active:translate-y-0",
    VARIANT[variant],
    iconOnly ? ICON_ONLY[size] : SIZE[size],
    block && "w-full",
  );
}

/** Primary, secondary, ghost and success buttons. Loading keeps the label in the layout (no width shift). */
export function Button({ variant = "secondary", size = "md", loading, icon: Icon, iconRight: IconRight, block, children, className, disabled, type, ...rest }: Base) {
  const px = ICON[size];
  return (
    <button
      type={type ?? "button"}
      className={cn(buttonClass(variant, size, block), className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      <span className={cn("inline-flex items-center justify-center gap-[inherit]", loading && "invisible")}>
        {Icon && <Icon size={px} aria-hidden strokeWidth={2.25} className="shrink-0" />}
        <span>{children}</span>
        {IconRight && <IconRight size={px} aria-hidden strokeWidth={2.25} className="shrink-0" />}
      </span>
      {loading && (
        <span className="absolute inset-0 inline-flex items-center justify-center" aria-hidden>
          <Loader2 size={px} className="animate-spin" />
        </span>
      )}
    </button>
  );
}

/** Danger action that asks once more before acting: the first press arms it, the second within 5 s confirms. */
export function DangerButton({ confirmLabel, onConfirm, children, size = "md", ...rest }: Omit<Base, "variant" | "onClick"> & { confirmLabel: string; onConfirm: () => void }) {
  const [armed, setArmed] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  return (
    <span className="inline-flex flex-col items-start gap-1">
      <Button
        {...rest}
        size={size}
        variant={armed ? "danger" : "danger-outline"}
        onClick={() => {
          if (armed) {
            window.clearTimeout(timer.current);
            setArmed(false);
            onConfirm();
          } else {
            setArmed(true);
            timer.current = window.setTimeout(() => setArmed(false), 5000);
          }
        }}
      >
        {armed ? confirmLabel : children}
      </Button>
      <span className="sr-only" aria-live="polite">{armed ? `Press again to ${confirmLabel.toLowerCase()}.` : ""}</span>
    </span>
  );
}

/** Icon-only button: the accessible label is required by the type. */
export function IconButton({ icon: Icon, label, variant = "ghost", size = "md", className, ...rest }:
  Omit<ComponentProps<"button">, "children" | "aria-label"> & { icon: LucideIcon; label: string; variant?: Variant; size?: Size }) {
  return (
    <button type="button" aria-label={label} title={label} className={cn(buttonClass(variant, size, false, true), className)} {...rest}>
      <Icon size={ICON[size]} aria-hidden strokeWidth={2.25} className="shrink-0" />
    </button>
  );
}

/** Two-state toggle with aria-pressed (sound on/off, larger text, show every rule). */
export function ToggleButton({ pressed, onPressedChange, icon: Icon, children, size = "md", className, ...rest }:
  Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onChange" | "children"> & { pressed: boolean; onPressedChange: (v: boolean) => void; icon?: LucideIcon; size?: Size; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={() => onPressedChange(!pressed)}
      className={cn(buttonClass("secondary", size), pressed && "border-teal bg-tint text-teal", className)}
      {...rest}
    >
      {Icon && <Icon size={ICON[size]} aria-hidden strokeWidth={2.25} />}
      <span>{children}</span>
    </button>
  );
}

/** Success state shown after a save: same footprint as the button it replaces. */
export function SuccessButton({ children, size = "md", ...rest }: Omit<Base, "variant" | "icon">) {
  return (
    <Button {...rest} size={size} variant="success" icon={Check}>
      {children}
    </Button>
  );
}
