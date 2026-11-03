import { useState } from "react";
import { Check, Delete } from "lucide-react";
import type { Schemas } from "../api/client";
import { Button } from "../components/Button";
import { Tile, tapFeedback } from "../components/Tile";
import { t, type Lang } from "../i18n/i18n";
import { cn } from "../lib/cn";

type Opt = Schemas["KioskOption"];
const UNSURE = "unsure";
const SKIPPED = "__skipped__";

export function ContinueButton({ lang, disabled, onClick, busy }: { lang: Lang; disabled?: boolean; onClick: () => void; busy?: boolean }) {
  return (
    <Button size="kiosk" variant="primary" icon={Check} disabled={disabled} loading={busy} onClick={onClick} block data-testid="continue">
      {t("continue", lang)}
    </Button>
  );
}

/** single_choice and yes_no_unsure: tap a tile to answer (yes/no only; "Not sure" sits in the secondary row). */
export function ChoiceTiles({ options, value, lang, onPick, busy }: { options: Opt[]; value: unknown; lang: Lang; onPick: (id: string) => void; busy: boolean }) {
  const [pressed, setPressed] = useState<string | null>(null);
  const cols = options.length <= 2 ? "sm:grid-cols-2" : options.length >= 5 ? "sm:grid-cols-2" : "";
  return (
    <div className={cn("grid gap-3", cols)}>
      {options.map((o) => (
        <Tile
          key={o.id}
          data-testid={`opt-${o.id}`}
          selected={pressed === o.id || (pressed === null && value === o.id)}
          selectedLabel={t("selected", lang)}
          disabled={busy && pressed !== o.id}
          onClick={() => {
            setPressed(o.id);
            onPick(o.id);
          }}
        >
          {o.label}
        </Tile>
      ))}
    </div>
  );
}

/** multi_choice: tiles toggle; "none" is exclusive (choosing it clears the others, choosing another clears it). */
export function MultiTiles({ options, value, lang, onSubmit, busy }: { options: Opt[]; value: unknown; lang: Lang; onSubmit: (ids: string[]) => void; busy: boolean }) {
  const [sel, setSel] = useState<string[]>(() => (Array.isArray(value) && !value.includes(UNSURE) ? (value as string[]) : []));
  const toggle = (id: string) =>
    setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : id === "none" ? ["none"] : [...s.filter((x) => x !== "none"), id]));
  return (
    <div className="flex flex-col gap-4">
      <p className="text-k-body text-muted">{t("pickMany", lang)}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {options.map((o) => (
          <Tile key={o.id} data-testid={`opt-${o.id}`} selected={sel.includes(o.id)} selectedLabel={t("selected", lang)} onClick={() => toggle(o.id)}>
            {o.label}
          </Tile>
        ))}
      </div>
      <ContinueButton lang={lang} disabled={!sel.length} busy={busy} onClick={() => onSubmit(options.map((o) => o.id).filter((id) => sel.includes(id)))} />
    </div>
  );
}

/** number: a big keypad with the allowed range shown. The server validates the range again. */
export function Keypad({ min, max, value, lang, onSubmit, busy }: { min: number; max: number; value: unknown; lang: Lang; onSubmit: (n: number) => void; busy: boolean }) {
  const [txt, setTxt] = useState(typeof value === "number" ? String(value) : "");
  const n = txt === "" || txt === "." ? null : Number(txt);
  const inRange = n !== null && !Number.isNaN(n) && n >= min && n <= max;
  const press = (k: string) => {
    tapFeedback();
    setTxt((s) => {
      if (k === "del") return s.slice(0, -1);
      if (k === "." && (s.includes(".") || s === "")) return s;
      if (s.replace(".", "").length >= 5) return s;
      return s === "0" && k !== "." ? k : s + k;
    });
  };
  const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", ".", "0", "del"];
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-baseline justify-between gap-3">
        <output aria-live="polite" className="min-h-20 flex-1 rounded-tile border-2 border-line-strong bg-surface px-5 py-2 text-[3.5rem] leading-none font-bold tabular" data-testid="keypad-value">
          {txt || <span className="text-line-strong">-</span>}
        </output>
      </div>
      <p className={cn("text-k-body", n !== null && !inRange ? "font-semibold text-red" : "text-muted")}>
        {n !== null && !inRange ? t("outOfRange", lang, { min, max }) : t("range", lang, { min, max })}
      </p>
      <div className="grid grid-cols-3 gap-3">
        {keys.map((k) => (
          <button
            key={k}
            type="button"
            data-testid={`key-${k}`}
            aria-label={k === "del" ? t("deleteDigit", lang) : k === "." ? "decimal point" : k}
            onClick={() => press(k)}
            className="flex min-h-18 items-center justify-center rounded-tile border-2 border-b-[5px] border-line-strong bg-surface text-[2rem] font-bold tabular transition-transform duration-(--dur-feedback) active:translate-y-[3px] active:border-b-2"
          >
            {k === "del" ? <Delete size={32} aria-hidden /> : k}
          </button>
        ))}
      </div>
      <ContinueButton lang={lang} disabled={!inRange} busy={busy} onClick={() => n !== null && onSubmit(n)} />
    </div>
  );
}

/** scale_0_10: eleven large buttons with the end labels in the patient's language. */
export function Scale({ value, lang, onPick, busy }: { value: unknown; lang: Lang; onPick: (n: number) => void; busy: boolean }) {
  const [pressed, setPressed] = useState<number | null>(null);
  const cur = pressed ?? (typeof value === "number" ? value : null);
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-6 gap-2 sm:grid-cols-11" role="radiogroup">
        {Array.from({ length: 11 }, (_, i) => (
          <button
            key={i}
            type="button"
            role="radio"
            aria-checked={cur === i}
            data-testid={`scale-${i}`}
            disabled={busy && pressed !== i}
            onClick={() => {
              tapFeedback();
              setPressed(i);
              onPick(i);
            }}
            className={cn(
              "flex min-h-18 items-center justify-center rounded-tile border-2 border-b-[5px] text-[1.75rem] font-bold tabular transition-transform duration-(--dur-feedback) active:translate-y-[3px] active:border-b-2",
              cur === i ? "border-teal border-b-teal-press bg-teal text-on-teal" : "border-line-strong bg-surface",
            )}
          >
            {i}
          </button>
        ))}
      </div>
      <div className="flex justify-between text-k-body font-semibold text-muted">
        <span>0 = {t("scaleLow", lang)}</span>
        <span>10 = {t("scaleHigh", lang)}</span>
      </div>
    </div>
  );
}

export function FreeText({ value, lang, onSubmit, busy }: { value: unknown; lang: Lang; onSubmit: (s: string) => void; busy: boolean }) {
  const [txt, setTxt] = useState(typeof value === "string" && value !== UNSURE && value !== SKIPPED ? value : "");
  return (
    <div className="flex flex-col gap-4">
      <label className="sr-only" htmlFor="kiosk-text">
        {t("typeHere", lang)}
      </label>
      <textarea
        id="kiosk-text"
        value={txt}
        onChange={(e) => setTxt(e.target.value)}
        placeholder={t("typeHere", lang)}
        rows={4}
        maxLength={500}
        className="min-h-40 w-full rounded-tile border-2 border-line-strong bg-surface p-4 text-k-tile"
      />
      <ContinueButton lang={lang} disabled={!txt.trim()} busy={busy} onClick={() => onSubmit(txt.trim())} />
    </div>
  );
}
