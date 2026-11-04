import { Fragment, useMemo, useState, type ReactNode } from "react";
import { ArrowDown, ArrowUp, ChevronRight } from "lucide-react";
import { cn } from "../lib/cn";

export type Column<T> = {
  key: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  sortValue?: (row: T) => string | number | null | undefined;
  className?: string;
  headerClassName?: string;
};

type Sort = { key: string; dir: "asc" | "desc" } | null;

/**
 * Generic table. Sortable headers expose aria-sort; the first column sticks while scrolling sideways; "select all" selects only
 * the rows currently shown (the filtered view); an optional expander renders details under a row.
 */
export function DataTable<T>({
  rows, columns, rowId, caption, initialSort = null, onRowClick, rowClassName, expand, selectable, selected, onSelectedChange, empty, footer,
}: {
  rows: T[];
  columns: Column<T>[];
  rowId: (r: T) => string;
  caption: string;
  initialSort?: Sort;
  onRowClick?: (r: T) => void;
  rowClassName?: (r: T) => string | undefined;
  expand?: (r: T) => ReactNode;
  selectable?: boolean;
  selected?: Set<string>;
  onSelectedChange?: (s: Set<string>) => void;
  empty?: ReactNode;
  footer?: ReactNode;
}) {
  const [sort, setSort] = useState<Sort>(initialSort);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.sortValue) return rows;
    const sv = col.sortValue;
    return [...rows].sort((a, b) => {
      const x = sv(a);
      const y = sv(b);
      if (x === y) return 0;
      if (x === null || x === undefined) return 1;
      if (y === null || y === undefined) return -1;
      const c = x < y ? -1 : 1;
      return sort.dir === "asc" ? c : -c;
    });
  }, [rows, columns, sort]);
  const ids = sorted.map(rowId);
  const allOn = selectable && ids.length > 0 && ids.every((i) => selected?.has(i));
  const someOn = selectable && ids.some((i) => selected?.has(i));
  const toggleAll = () => {
    const next = new Set(selected);
    if (allOn) ids.forEach((i) => next.delete(i));
    else ids.forEach((i) => next.add(i));
    onSelectedChange?.(next);
  };
  const colCount = columns.length + (selectable ? 1 : 0) + (expand ? 1 : 0);
  return (
    <div className="overflow-x-auto rounded-panel border border-line bg-surface">
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="bg-tint text-left">
          <tr>
            {expand && <th scope="col" className="w-10"><span className="sr-only">Details</span></th>}
            {selectable && (
              <th scope="col" className="w-10 px-3">
                <input
                  type="checkbox"
                  aria-label="Select all shown rows"
                  checked={!!allOn}
                  ref={(el) => {
                    if (el) el.indeterminate = !allOn && !!someOn;
                  }}
                  onChange={toggleAll}
                  className="size-4 accent-(--teal)"
                />
              </th>
            )}
            {columns.map((c, i) => {
              const s = sort?.key === c.key ? sort.dir : null;
              return (
                <th
                  key={c.key}
                  scope="col"
                  aria-sort={c.sortValue ? (s === "asc" ? "ascending" : s === "desc" ? "descending" : "none") : undefined}
                  className={cn("whitespace-nowrap px-3 py-2 text-xs font-semibold text-muted", i === 0 && !expand && !selectable && "sticky left-0 z-10 bg-tint", c.headerClassName)}
                >
                  {c.sortValue ? (
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 hover:text-ink"
                      onClick={() => setSort(s === "asc" ? { key: c.key, dir: "desc" } : s === "desc" ? null : { key: c.key, dir: "asc" })}
                    >
                      {c.header}
                      {s === "asc" ? <ArrowUp size={13} aria-hidden /> : s === "desc" ? <ArrowDown size={13} aria-hidden /> : null}
                    </button>
                  ) : (
                    c.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.length === 0 && (
            <tr>
              <td colSpan={colCount} className="p-4">
                {empty}
              </td>
            </tr>
          )}
          {sorted.map((r) => {
            const id = rowId(r);
            const isOpen = open.has(id);
            return (
              <Fragment key={id}>
                <tr
                  className={cn("border-t border-line", onRowClick && "cursor-pointer hover:bg-tint/60", rowClassName?.(r))}
                  onClick={onRowClick ? () => onRowClick(r) : undefined}
                >
                  {expand && (
                    <td className="w-10 px-1">
                      <button
                        type="button"
                        aria-expanded={isOpen}
                        aria-label={isOpen ? "Hide details" : "Show details"}
                        onClick={(e) => {
                          e.stopPropagation();
                          setOpen((o) => {
                            const n = new Set(o);
                            if (n.has(id)) n.delete(id);
                            else n.add(id);
                            return n;
                          });
                        }}
                        className="inline-flex size-8 items-center justify-center rounded-field hover:bg-tint"
                      >
                        <ChevronRight size={16} aria-hidden className={cn("transition-transform duration-(--dur-feedback)", isOpen && "rotate-90")} />
                      </button>
                    </td>
                  )}
                  {selectable && (
                    <td className="w-10 px-3" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        aria-label={`Select ${id}`}
                        checked={!!selected?.has(id)}
                        onChange={() => {
                          const n = new Set(selected);
                          if (n.has(id)) n.delete(id);
                          else n.add(id);
                          onSelectedChange?.(n);
                        }}
                        className="size-4 accent-(--teal)"
                      />
                    </td>
                  )}
                  {columns.map((c, i) => (
                    <td key={c.key} className={cn("px-3 py-2 align-top", i === 0 && !expand && !selectable && "sticky left-0 bg-surface", c.className)}>
                      {c.cell(r)}
                    </td>
                  ))}
                </tr>
                {expand && isOpen && (
                  <tr className="bg-paper">
                    <td colSpan={colCount} className="px-4 py-3">
                      {expand(r)}
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
      {footer}
    </div>
  );
}
