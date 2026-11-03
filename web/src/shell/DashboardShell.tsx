import { useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { LogOut, Menu, Monitor, Moon, PanelLeftClose, PanelLeftOpen, Sun, X, type LucideIcon } from "lucide-react";
import { post, type Me } from "../api/client";
import { IconButton } from "../components/Button";
import { OfflineBadge } from "../components/OfflineBadge";
import { cn } from "../lib/cn";
import { useTheme, type ThemePref } from "./theme";

export type NavItem = { to: string; label: string; icon: LucideIcon; count?: number; end?: boolean };

function useStored(key: string, init: boolean): [boolean, (v: boolean) => void] {
  const [v, setV] = useState<boolean>(() => {
    try {
      const s = localStorage.getItem(key);
      return s === null ? init : s === "1";
    } catch {
      return init;
    }
  });
  return [
    v,
    (n) => {
      setV(n);
      try {
        localStorage.setItem(key, n ? "1" : "0");
      } catch {
        /* ignore */
      }
    },
  ];
}

export function ThemeSwitch() {
  const [pref, setPref] = useTheme();
  const opts: { v: ThemePref; label: string; icon: LucideIcon }[] = [
    { v: "light", label: "Light theme", icon: Sun },
    { v: "dark", label: "Dark theme", icon: Moon },
    { v: "system", label: "Use system theme", icon: Monitor },
  ];
  return (
    <div role="radiogroup" aria-label="Theme" className="inline-flex rounded-full border border-line bg-surface p-0.5">
      {opts.map((o) => (
        <button
          key={o.v}
          type="button"
          role="radio"
          aria-checked={pref === o.v}
          aria-label={o.label}
          title={o.label}
          onClick={() => setPref(o.v)}
          className={cn("inline-flex size-7 items-center justify-center rounded-full", pref === o.v ? "bg-teal text-on-teal" : "text-muted hover:text-ink")}
        >
          <o.icon size={15} aria-hidden />
        </button>
      ))}
    </div>
  );
}

function NavList({ items, collapsed, onNavigate }: { items: NavItem[]; collapsed: boolean; onNavigate?: () => void }) {
  return (
    <ul className="flex flex-col gap-0.5">
      {items.map((it) => (
        <li key={it.to}>
          <NavLink
            to={it.to}
            end={it.end}
            onClick={onNavigate}
            title={collapsed ? it.label : undefined}
            className={({ isActive }) =>
              cn(
                "flex min-h-10 items-center gap-3 rounded-field px-3 text-base font-semibold",
                isActive ? "bg-tint text-teal" : "text-muted hover:bg-tint hover:text-ink",
                collapsed && "justify-center px-0",
              )
            }
          >
            <it.icon size={19} aria-hidden className="shrink-0" />
            <span className={cn(collapsed && "sr-only")}>{it.label}</span>
            {it.count ? (
              <span className={cn("ml-auto rounded-full bg-marigold px-1.5 text-xs font-bold text-on-marigold tabular", collapsed && "absolute ml-6 -mt-6")}>
                {it.count}
              </span>
            ) : null}
          </NavLink>
        </li>
      ))}
    </ul>
  );
}

/** Staff and doctor layout: collapsible sidebar (persisted), sticky header, drawer below md with focus trap and Esc. */
export function DashboardShell({ area, title, nav, me, headerExtra, children }: { area: string; title: string; nav: NavItem[]; me: Me; headerExtra?: ReactNode; children: ReactNode }) {
  const [collapsed, setCollapsed] = useStored(`mk.sidebar.${area}`, false);
  const [drawer, setDrawer] = useState(false);
  const drawerRef = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLButtonElement>(null);
  const loc = useLocation();
  const qc = useQueryClient();

  useEffect(() => setDrawer(false), [loc.pathname]);
  useEffect(() => {
    if (!drawer) return;
    const el = drawerRef.current;
    const focusables = () => Array.from(el?.querySelectorAll<HTMLElement>("a,button,[tabindex]:not([tabindex='-1'])") ?? []);
    focusables()[0]?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setDrawer(false);
        return;
      }
      if (e.key !== "Tab") return;
      const f = focusables();
      if (!f.length) return;
      const first = f[0]!;
      const last = f[f.length - 1]!;
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    const back = opener.current;
    return () => {
      document.removeEventListener("keydown", onKey);
      back?.focus();
    };
  }, [drawer]);

  const signOut = async () => {
    await post("/api/auth/logout").catch(() => undefined);
    qc.setQueryData(["me"], null);
  };

  const brand = (
    <div className="flex min-h-14 items-center gap-2 px-3">
      <span className="inline-flex size-8 shrink-0 items-center justify-center rounded-field bg-teal text-on-teal" aria-hidden>
        <svg viewBox="0 0 32 32" className="size-5" fill="currentColor">
          <path d="M13 7h6v6h6v6h-6v6h-6v-6H7v-6h6z" />
        </svg>
      </span>
      <span className={cn("leading-tight", collapsed && "md:sr-only")}>
        <span className="block text-sm font-bold">MediKiosk OPD</span>
        <span className="block text-xs text-muted">{title}</span>
      </span>
    </div>
  );

  return (
    <div className="min-h-dvh bg-paper text-ink md:flex">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded-field focus:bg-surface focus:p-2">
        Skip to content
      </a>
      <aside className={cn("sticky top-0 hidden h-dvh shrink-0 flex-col border-r border-line bg-surface md:flex", collapsed ? "w-16" : "w-60")} aria-label={`${title} navigation`}>
        {brand}
        <nav className="flex-1 overflow-y-auto px-2 py-2">
          <NavList items={nav} collapsed={collapsed} />
        </nav>
        <div className={cn("border-t border-line p-2", collapsed && "flex justify-center")}>
          <IconButton icon={collapsed ? PanelLeftOpen : PanelLeftClose} label={collapsed ? "Expand sidebar" : "Collapse sidebar"} onClick={() => setCollapsed(!collapsed)} />
        </div>
      </aside>

      {drawer && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-ink/40" onClick={() => setDrawer(false)} aria-hidden />
          <div ref={drawerRef} role="dialog" aria-modal="true" aria-label={`${title} navigation`} className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col bg-surface shadow-(--shadow-overlay)">
            <div className="flex items-center justify-between pr-2">
              {brand}
              <IconButton icon={X} label="Close menu" onClick={() => setDrawer(false)} />
            </div>
            <nav className="flex-1 overflow-y-auto px-2 py-2">
              <NavList items={nav} collapsed={false} onNavigate={() => setDrawer(false)} />
            </nav>
          </div>
        </div>
      )}

      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-30 flex min-h-14 flex-wrap items-center gap-2 border-b border-line bg-paper/95 px-3 py-2 backdrop-blur md:px-6">
          <span className="md:hidden">
            <IconButton icon={Menu} label="Open menu" onClick={() => setDrawer(true)} ref={opener} />
          </span>
          <div className="min-w-0 flex-1">{headerExtra}</div>
          <OfflineBadge />
          <ThemeSwitch />
          <div className="flex items-center gap-1 rounded-full border border-line bg-surface py-0.5 pl-3 pr-0.5">
            <span className="text-xs">
              <span className="font-semibold">{me.username}</span> <span className="text-muted">{me.role}</span>
            </span>
            <IconButton icon={LogOut} label="Sign out" size="sm" onClick={signOut} />
          </div>
        </header>
        <main id="main" className="mx-auto w-full max-w-[1400px] px-3 py-4 md:px-6 md:py-6">
          {children}
        </main>
      </div>
    </div>
  );
}
