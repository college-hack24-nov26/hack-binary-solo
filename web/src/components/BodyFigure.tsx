import type { BodyRegions } from "../api/client";
import type { Lang } from "../i18n/i18n";

/**
 * Original body figure drawn from data/body_regions.json polygons (no third-party art). `fills` maps region id -> colour.
 * With `onTap`, each region is a focusable button (Enter/Space toggles). Side labels name the PATIENT's side.
 */
export function BodyFigure({
  catalog, view, fills = {}, onTap, lang, className, labelledBy, showSides = true,
}: {
  catalog: BodyRegions; view: "front" | "back"; fills?: Record<string, string>; onTap?: (id: string) => void; lang: Lang; className?: string; labelledBy?: string; showSides?: boolean;
}) {
  const [w, h] = catalog.viewBox as [number, number];
  const regions = catalog.regions.filter((r) => r.view === view);
  const viewerLeft = view === "front" ? "right" : "left";       // whose side is on the viewer's left
  const viewerRight = view === "front" ? "left" : "right";
  const side = (s: string) => catalog.sideLabels[s]?.[lang] ?? catalog.sideLabels[s]?.en ?? s;
  return (
    <svg
      viewBox={`0 0 ${w} ${h + (showSides ? 22 : 0)}`}
      className={className}
      role={onTap ? "group" : "img"}
      aria-labelledby={labelledBy}
      aria-label={labelledBy ? undefined : catalog.viewLabels[view]?.[lang]}
      style={{ touchAction: "manipulation" }}
    >
      {regions.map((r) => {
        const fill = fills[r.id];
        const label = r.label[lang] ?? r.label.en ?? r.id;
        const pts = r.polygon.map(([x, y]) => `${x},${y}`).join(" ");
        return (
          <polygon
            key={r.id}
            points={pts}
            data-testid={`region-${r.id}`}
            data-region={r.id}
            fill={fill ?? "var(--surface)"}
            fillOpacity={fill ? 0.9 : 1}
            stroke="var(--line-strong)"
            strokeWidth={1.1}
            strokeLinejoin="round"
            className={onTap ? "cursor-pointer outline-none transition-[fill] duration-(--dur-feedback) hover:fill-tint focus-visible:stroke-teal focus-visible:[stroke-width:3]" : undefined}
            role={onTap ? "button" : undefined}
            tabIndex={onTap ? 0 : undefined}
            aria-pressed={onTap ? Boolean(fill) : undefined}
            aria-label={onTap ? label : undefined}
            onClick={onTap ? () => onTap(r.id) : undefined}
            onKeyDown={
              onTap
                ? (e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onTap(r.id);
                    }
                  }
                : undefined
            }
          >
            <title>{label}</title>
          </polygon>
        );
      })}
      {showSides && (
        <>
          <text x={2} y={h + 16} fontSize={11} fontWeight={600} fill="var(--muted)">
            {side(viewerLeft)}
          </text>
          <text x={w - 2} y={h + 16} fontSize={11} fontWeight={600} textAnchor="end" fill="var(--muted)">
            {side(viewerRight)}
          </text>
        </>
      )}
    </svg>
  );
}
