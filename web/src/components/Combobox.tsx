import { useId, useMemo, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "../lib/cn";

export type Option = { value: string; label: string; hint?: string };

/** Searchable single-select (ARIA 1.2 combobox with a listbox popup). Arrow keys, Enter, Escape. */
export function Combobox({ label, options, value, onChange, placeholder, id: idProp }: { label: string; options: Option[]; value: string | null; onChange: (v: string) => void; placeholder?: string; id?: string }) {
  const auto = useId();
  const id = idProp ?? auto;
  const selected = options.find((o) => o.value === value);
  const [text, setText] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const shown = useMemo(() => {
    const q = (text ?? "").trim().toLowerCase();
    return q ? options.filter((o) => o.label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q)) : options;
  }, [options, text]);
  const pick = (o: Option) => {
    onChange(o.value);
    setText(null);
    setOpen(false);
  };
  return (
    <div className="relative flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-semibold">
        {label}
      </label>
      <div className="relative">
        <input
          ref={input}
          id={id}
          role="combobox"
          aria-expanded={open}
          aria-controls={`${id}-list`}
          aria-autocomplete="list"
          aria-activedescendant={open && shown[active] ? `${id}-o-${shown[active].value}` : undefined}
          value={text ?? selected?.label ?? ""}
          placeholder={placeholder}
          autoComplete="off"
          onFocus={(e) => {
            e.currentTarget.select();
            setOpen(true);
          }}
          onBlur={() => window.setTimeout(() => setOpen(false), 120)}
          onChange={(e) => {
            setText(e.target.value);
            setActive(0);
            setOpen(true);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setOpen(true);
              setActive((a) => Math.min(a + 1, shown.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, 0));
            } else if (e.key === "Enter" && open && shown[active]) {
              e.preventDefault();
              pick(shown[active]);
            } else if (e.key === "Escape") {
              setText(null);
              setOpen(false);
            }
          }}
          className="min-h-10 w-full rounded-field border border-line-strong bg-surface px-3 pr-9 text-base"
        />
        <ChevronDown size={16} aria-hidden className="pointer-events-none absolute right-3 top-3 text-muted" />
      </div>
      {open && (
        <ul id={`${id}-list`} role="listbox" aria-label={label} className="absolute top-full z-30 mt-1 max-h-72 w-full overflow-auto rounded-panel border border-line bg-surface py-1 shadow-(--shadow-overlay)">
          {shown.length === 0 && <li className="px-3 py-2 text-sm text-muted">No match. Check the spelling.</li>}
          {shown.map((o, i) => (
            <li
              key={o.value}
              id={`${id}-o-${o.value}`}
              role="option"
              aria-selected={o.value === value}
              onMouseDown={(e) => {
                e.preventDefault();
                pick(o);
              }}
              onMouseEnter={() => setActive(i)}
              className={cn("flex cursor-pointer items-baseline justify-between gap-3 px-3 py-2 text-base", i === active && "bg-tint", o.value === value && "font-semibold text-teal")}
            >
              <span>{o.label}</span>
              {o.hint && <span className="text-xs text-muted">{o.hint}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
