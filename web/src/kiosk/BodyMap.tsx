import { useState } from "react";
import { List, PersonStanding } from "lucide-react";
import type { BodyRegions } from "../api/client";
import { BodyFigure } from "../components/BodyFigure";
import { Button } from "../components/Button";
import { Chip } from "../components/ui";
import { Tile, tapFeedback } from "../components/Tile";
import { t, type Lang } from "../i18n/i18n";
import { cn } from "../lib/cn";
import { ContinueButton } from "./inputs";

/**
 * Tap the body (front/back) or choose from a list. Selected regions fill teal and show as removable chips in the patient's
 * language. The browser only highlights; the server builds and validates the answer (bodymap.make_answer).
 */
export function BodyMap({ catalog, maxSelections, value, lang, busy, onSubmit }: {
  catalog: BodyRegions; maxSelections: number; value: unknown; lang: Lang; busy: boolean;
  onSubmit: (a: { regions: string[]; view: "front" | "back"; inputMode: "map" | "list" }) => void;
}) {
  const cur = (value && typeof value === "object" ? value : {}) as { regions?: string[]; view?: "front" | "back"; inputMode?: "map" | "list" };
  const [sel, setSel] = useState<string[]>(cur.regions ?? []);
  const [view, setView] = useState<"front" | "back">(cur.view ?? "front");
  const [mode, setMode] = useState<"map" | "list">(cur.inputMode ?? "map");
  const [tooMany, setTooMany] = useState(false);
  const label = (id: string) => catalog.regions.find((r) => r.id === id)?.label[lang] ?? id;
  const toggle = (id: string, via: "map" | "list") => {
    tapFeedback();
    setTooMany(false);
    setSel((s) => {
      if (s.includes(id)) return s.filter((x) => x !== id);
      if (s.length >= maxSelections) {
        setTooMany(true);
        return s;
      }
      return [...s, id];
    });
    setMode(via);
  };
  const fills = Object.fromEntries(sel.map((id) => [id, "var(--teal)"]));
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <div role="radiogroup" aria-label="Front or back" className="inline-flex rounded-full border-2 border-line-strong bg-surface p-1">
          {(["front", "back"] as const).map((v) => (
            <button
              key={v}
              type="button"
              role="radio"
              aria-checked={view === v}
              onClick={() => setView(v)}
              className={cn("min-h-16 min-w-28 rounded-full px-5 text-k-tile font-semibold", view === v ? "bg-teal text-on-teal" : "text-ink")}
            >
              {catalog.viewLabels[v]?.[lang]}
            </button>
          ))}
        </div>
        <Button size="kiosk" variant="secondary" icon={mode === "map" ? List : PersonStanding} onClick={() => setMode(mode === "map" ? "list" : "map")} data-testid="bm-toggle-list">
          {mode === "map" ? t("bmList", lang) : t("bmMap", lang)}
        </Button>
      </div>

      {mode === "map" ? (
        <div className="flex flex-col items-center gap-2">
          <p className="self-start text-k-body text-muted">{t("bmTap", lang)}</p>
          <BodyFigure catalog={catalog} view={view} fills={fills} onTap={(id) => toggle(id, "map")} lang={lang} showSides={false} className="h-[min(54vh,36rem)] w-auto max-w-full" />
          <p className="flex w-full max-w-sm justify-between text-k-body font-semibold text-muted" aria-hidden>
            <span>{view === "front" ? t("patientRight", lang) : t("patientLeft", lang)}</span>
            <span>{view === "front" ? t("patientLeft", lang) : t("patientRight", lang)}</span>
          </p>
        </div>
      ) : (
        <div className="grid max-h-[50vh] gap-2 overflow-y-auto pr-1 sm:grid-cols-2">
          {catalog.regions
            .filter((r) => r.view === view)
            .map((r) => (
              <Tile key={r.id} data-testid={`list-${r.id}`} selected={sel.includes(r.id)} selectedLabel={t("selected", lang)} onClick={() => toggle(r.id, "list")} className="min-h-16 py-2">
                {r.label[lang] ?? r.label.en}
              </Tile>
            ))}
        </div>
      )}

      <div aria-live="polite" className="flex min-h-14 flex-wrap items-center gap-2">
        {tooMany && <p className="w-full text-k-body font-semibold text-red">{t("bmMax", lang, { n: maxSelections })}</p>}
        {sel.length === 0 ? (
          <p className="text-k-body text-muted">{t("bmNone", lang)}</p>
        ) : (
          <>
            <span className="sr-only">{t("bmChosen", lang)}:</span>
            {sel.map((id) => (
              <Chip key={id} onRemove={() => toggle(id, mode)} removeLabel={t("remove", lang, { x: label(id) })}>
                {label(id)}
              </Chip>
            ))}
          </>
        )}
      </div>
      <ContinueButton lang={lang} disabled={!sel.length} busy={busy} onClick={() => onSubmit({ regions: sel, view: catalog.regions.find((r) => r.id === sel[0])?.view ?? view, inputMode: mode })} />
    </div>
  );
}
