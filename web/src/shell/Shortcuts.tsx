import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { IconButton } from "../components/Button";

function typing(e: KeyboardEvent) {
  const t = e.target as HTMLElement | null;
  return !!t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable);
}

/** "?" opens the shortcut list; "g" then a letter navigates. Ignored while typing in a field. */
export function ShortcutsOverlay({ items, go }: { items: [string, string][]; go: Record<string, () => void> }) {
  const [open, setOpen] = useState(false);
  const pendingG = useRef(0);
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
      if (typing(e) || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "?") {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === "g") pendingG.current = Date.now();
      else if (Date.now() - pendingG.current < 1200 && go[e.key]) {
        pendingG.current = 0;
        go[e.key]!();
      } else if (e.key === "/") {
        const s = document.querySelector<HTMLInputElement>("[data-shortcut=search]");
        if (s) {
          e.preventDefault();
          s.focus();
        }
      } else if (e.key === "n") document.querySelector<HTMLElement>("[data-shortcut=next]")?.click();
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [go]);
  useEffect(() => {
    if (open) closeRef.current?.focus();
  }, [open]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4" onClick={() => setOpen(false)}>
      <div role="dialog" aria-modal="true" aria-labelledby="kb-h" className="w-full max-w-sm rounded-panel border border-line bg-surface p-5 shadow-(--shadow-overlay)" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <h2 id="kb-h" className="text-lg font-semibold">
            Keyboard shortcuts
          </h2>
          <IconButton ref={closeRef} icon={X} label="Close shortcuts" onClick={() => setOpen(false)} />
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
          {items.map(([k, v]) => (
            <div key={k} className="contents">
              <dt>
                <kbd className="rounded-field border border-line-strong bg-tint px-1.5 py-0.5 font-mono text-xs">{k}</kbd>
              </dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
