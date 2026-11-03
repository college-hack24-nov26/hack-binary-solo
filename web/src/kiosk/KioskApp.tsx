import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, BellRing, Contrast, Hand, Languages, Pencil, Printer, RotateCcw, Type, Volume2 } from "lucide-react";
import { ApiError, type DoctorOut, type KioskScreen, type ReviewItem, type TokenSlip as Slip } from "../api/client";
import { Button, ToggleButton } from "../components/Button";
import { Tile } from "../components/Tile";
import { TokenSlip, WayStrip } from "../components/TokenSlip";
import { LANG_NAMES, LANGS, t, type Lang } from "../i18n/i18n";
import { cn } from "../lib/cn";
import { useBodyRegions, useDoctors } from "../lib/hooks";
import { BodyMap } from "./BodyMap";
import { ChoiceTiles, FreeText, Keypad, MultiTiles, Scale } from "./inputs";
import { clearSaved, createSession, kioskClient, loadSaved, save, type Saved } from "./kioskApi";
import { speak, stopSpeaking, useLocalVoice } from "./speech";

const IDLE_MS = 90_000;
const COUNTDOWN_S = 30;
const SLIP_RESET_S = 60;
const UNSURE = "unsure";

type Stage = { kind: "language" } | { kind: "screen"; screen: KioskScreen; dir: "fwd" | "back" } | { kind: "review"; items: ReviewItem[] } | { kind: "doctor" } | { kind: "slip"; slip: Slip | null; error: string | null };

export default function KioskApp() {
  const [saved, setSaved] = useState<Saved | null>(() => loadSaved());
  const [stage, setStage] = useState<Stage>({ kind: "language" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [large, setLarge] = useState(false);
  const [contrast, setContrast] = useState(false);
  const [langOpen, setLangOpen] = useState(false);
  const [help, setHelp] = useState<"sent" | "failed" | null>(null);
  const [idle, setIdle] = useState<number | null>(null);
  const lang: Lang = saved?.lang ?? "en";
  const client = saved ? kioskClient(saved) : null;
  const voice = useLocalVoice(lang);
  const regions = useBodyRegions();
  const doctors = useDoctors();

  // ---- reset: clear the tablet's copy of the session and go back to the language screen (the record stays for staff)
  const reset = useCallback(() => {
    clearSaved();
    stopSpeaking();
    setSaved(null);
    setStage({ kind: "language" });
    setError(null);
    setLarge(false);
    setContrast(false);
    setHelp(null);
    setIdle(null);
    setLangOpen(false);
    window.scrollTo(0, 0);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("kiosk-large", large);
    return () => document.documentElement.classList.remove("kiosk-large");
  }, [large]);
  useEffect(() => {
    document.documentElement.classList.remove("dark");    // the kiosk is always light
    document.documentElement.lang = lang;
  }, [lang]);

  // ---- resume after a reload
  useEffect(() => {
    if (!saved || stage.kind !== "language") return;
    kioskClient(saved).screen().then((s) => show(s), () => reset());
  }, []); // once, on load

  // ---- idle: 90 s without a touch shows "Are you still there?" with a 30 s countdown, then resets
  const lastTouch = useRef(Date.now());
  useEffect(() => {
    const touch = () => {
      lastTouch.current = Date.now();
    };
    const evs = ["pointerdown", "keydown", "input"] as const;
    evs.forEach((e) => window.addEventListener(e, touch, { passive: true }));
    const id = window.setInterval(() => {
      if (stage.kind === "language" || stage.kind === "slip") return;
      const quiet = Date.now() - lastTouch.current;
      if (quiet > IDLE_MS) {
        const left = COUNTDOWN_S - Math.floor((quiet - IDLE_MS) / 1000);
        if (left <= 0) reset();
        else setIdle(left);
      } else setIdle(null);
    }, 500);
    return () => {
      evs.forEach((e) => window.removeEventListener(e, touch));
      window.clearInterval(id);
    };
  }, [stage.kind, reset]);

  const run = async <T,>(fn: () => Promise<T>, then: (v: T) => void) => {
    setBusy(true);
    setError(null);
    try {
      then(await fn());
    } catch (e) {
      if (e instanceof ApiError && (e.status === 401 || e.status === 404)) reset();
      else setError(e instanceof ApiError && e.status === 422 ? e.message : t("error", lang));
    } finally {
      setBusy(false);
    }
  };

  const show = (s: KioskScreen, dir: "fwd" | "back" = "fwd") => {
    window.scrollTo(0, 0);
    if (s.stage === "review") {
      run(() => kioskClient(saved!).review(), (r) => setStage({ kind: "review", items: r.items }));
    } else setStage({ kind: "screen", screen: s, dir });
  };

  const start = (l: Lang) =>
    run(() => createSession(l), (c) => {
      const s = { token: c.token, kioskKey: c.kioskKey, lang: l };
      save(s);
      setSaved(s);
      lastTouch.current = Date.now();
      setStage({ kind: "screen", screen: c.screen, dir: "fwd" });
    });

  const changeLanguage = (l: Lang) => {
    setLangOpen(false);
    if (!saved) return;
    const node = stage.kind === "screen" ? stage.screen.node?.id : undefined;
    run(() => kioskClient(saved).language(l, node), (s) => {
      const ns = { ...saved, lang: l };
      save(ns);
      setSaved(ns);
      if (stage.kind === "screen") setStage({ ...stage, screen: s });
      else if (stage.kind === "review") show(s);
    });
  };

  const callHelp = () => {
    if (!client) return;
    client.help().then(() => setHelp("sent"), () => setHelp("failed"));
  };

  const current = stage.kind === "screen" ? stage.screen : null;
  const canBack = stage.kind === "review" || stage.kind === "doctor" || (current && (current.canGoBack || current.stage === "consent"));
  const back = () => {
    if (!client) return;
    if (stage.kind === "doctor") return run(() => client.review(), (r) => setStage({ kind: "review", items: r.items }));
    if (current?.stage === "consent" || current?.stage === "declined") return reset();
    run(() => client.back(current?.node?.id ?? null), (s) => show(s, "back"));
  };
  const questionText = current?.node?.text ?? "";

  if (stage.kind === "language") return <LanguageScreen onPick={start} busy={busy} error={error} />;

  return (
    <div className={cn("force-light kiosk-root flex min-h-dvh flex-col overflow-x-clip bg-paper text-ink", contrast && "kiosk-contrast")} lang={lang}>
      <header className="sticky top-0 z-20 flex flex-wrap items-center gap-2 border-b border-line bg-paper/95 px-3 py-3 backdrop-blur sm:px-4 no-print">
        {canBack && stage.kind !== "slip" ? (
          <Button size="kiosk" icon={ArrowLeft} onClick={back} disabled={busy} data-testid="back">
            {t("back", lang)}
          </Button>
        ) : (
          <span className="min-w-1" />
        )}
        <div className="flex-1" />
        {voice && questionText && (
          <Button size="kiosk" variant="ghost" icon={Volume2} onClick={() => speak(voice, [questionText, ...(current?.node?.options ?? []).map((o) => o.label)].join(". "))} aria-label={t("listen", lang)} className="px-4 sm:px-6">
            <span className="hidden sm:inline">{t("listen", lang)}</span>
          </Button>
        )}
        <Button size="kiosk" variant="secondary" icon={Languages} onClick={() => setLangOpen(true)} data-testid="change-language" aria-label={t("changeLanguage", lang)} className="px-4 sm:px-6">
          <span className="hidden sm:inline">{t("changeLanguage", lang)}</span>
        </Button>
        <Button size="kiosk" variant="secondary" icon={BellRing} onClick={callHelp} data-testid="help" aria-label={t("help", lang)} className="px-4 sm:px-6">
          <span className="hidden sm:inline">{t("help", lang)}</span>
        </Button>
      </header>
      {current && current.stage === "question" && (
        <div className="h-2 bg-tint no-print" role="progressbar" aria-label={t("progress", lang)} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round((100 * current.progress.done) / Math.max(1, current.progress.total))}>
          <div className="h-full bg-teal transition-[width] duration-(--dur-screen) ease-std" style={{ width: `${(100 * current.progress.done) / Math.max(1, current.progress.total)}%` }} />
        </div>
      )}

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-5 py-6 sm:px-8">
        {help && (
          <p role="status" className="flex items-center gap-3 rounded-tile border-2 border-on-marigold/30 bg-marigold-tint px-5 py-4 text-k-body font-semibold no-print">
            <BellRing size={28} aria-hidden className="shrink-0" />
            {help === "sent" ? t("helpSent", lang) : t("helpFailed", lang)}
          </p>
        )}
        {error && (
          <div role="alert" className="flex flex-wrap items-center gap-4 rounded-tile border-2 border-red bg-red-tint px-5 py-4 no-print">
            <p className="flex-1 text-k-body font-semibold">{error}</p>
            <Button size="kiosk" icon={RotateCcw} onClick={() => setError(null)}>
              {t("retry", lang)}
            </Button>
          </div>
        )}
        {stage.kind === "screen" && (
          <QuestionScreen
            key={`${stage.screen.node?.id ?? stage.screen.stage}-${lang}`}
            s={stage.screen}
            dir={stage.dir}
            lang={lang}
            busy={busy}
            regions={regions.data}
            onConsent={(c) => run(() => client!.consent(c), (s) => show(s))}
            onAnswer={(v) => run(() => client!.answer(stage.screen.node!.id, v), (s) => show(s))}
            onBodyMap={(b) => run(() => client!.bodymap({ nodeId: stage.screen.node!.id, ...b }), (s) => show(s))}
            onSkip={() => run(() => client!.skip(stage.screen.node!.id), (s) => show(s))}
            onRestart={reset}
          />
        )}
        {stage.kind === "review" && (
          <Review
            items={stage.items}
            lang={lang}
            onEdit={(nid) => run(() => client!.screen(nid), (s) => setStage({ kind: "screen", screen: s, dir: "back" }))}
            onConfirm={() => setStage({ kind: "doctor" })}
          />
        )}
        {stage.kind === "doctor" && (
          <DoctorChoice
            doctors={doctors.data ?? []}
            lang={lang}
            busy={busy}
            onPick={(id) =>
              run(() => client!.doctor(id), () => {
                setStage({ kind: "slip", slip: null, error: null });
                client!.finish().then(
                  (slip) => setStage({ kind: "slip", slip, error: null }),
                  () => setStage({ kind: "slip", slip: null, error: t("error", lang) }),
                );
              })
            }
          />
        )}
        {stage.kind === "slip" && (
          <SlipScreen
            stage={stage}
            lang={lang}
            onRetry={() => {
              setStage({ kind: "slip", slip: null, error: null });
              client!.finish().then(
                (slip) => setStage({ kind: "slip", slip, error: null }),
                () => setStage({ kind: "slip", slip: null, error: t("error", lang) }),
              );
            }}
            onDone={reset}
          />
        )}
      </main>

      <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-line px-4 py-3 no-print">
        <ToggleButton pressed={large} onPressedChange={setLarge} icon={Type} size="kiosk">
          {t("largerText", lang)}
        </ToggleButton>
        <ToggleButton pressed={contrast} onPressedChange={setContrast} icon={Contrast} size="kiosk">
          {t("highContrast", lang)}
        </ToggleButton>
      </footer>

      {langOpen && (
        <Sheet onClose={() => setLangOpen(false)} label={t("chooseLanguage", lang)}>
          <h2 className="text-k-lead font-bold">{t("chooseLanguage", lang)}</h2>
          <div className="mt-4 grid gap-3">
            {LANGS.map((l) => (
              <Tile key={l} lang={l} selected={l === lang} selectedLabel={t("selected", l)} onClick={() => changeLanguage(l)}>
                {LANG_NAMES[l]}
              </Tile>
            ))}
          </div>
        </Sheet>
      )}
      {idle !== null && (
        <Sheet onClose={() => setIdle(null)} label={t("stillThere", lang)} alert>
          <h2 className="text-k-question font-bold">{t("stillThere", lang)}</h2>
          <p className="mt-3 text-k-lead tabular">{t("stillThereBody", lang, { s: idle })}</p>
          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            <Button size="kiosk" variant="primary" onClick={() => setIdle(null)} data-testid="still-here">
              {t("continue", lang)}
            </Button>
            <Button size="kiosk" icon={RotateCcw} onClick={reset}>
              {t("startOver", lang)}
            </Button>
          </div>
        </Sheet>
      )}
    </div>
  );
}

function Sheet({ children, onClose, label, alert }: { children: ReactNode; onClose: () => void; label: string; alert?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.querySelector<HTMLElement>("button")?.focus();
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 grid place-items-end bg-ink/50 p-4 sm:place-items-center" onClick={onClose}>
      <div ref={ref} role={alert ? "alertdialog" : "dialog"} aria-modal="true" aria-label={label} className="animate-fade w-full max-w-xl rounded-tile bg-paper p-6 shadow-(--shadow-overlay)" onClick={(e) => e.stopPropagation()}>
        {children}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- language
function LanguageScreen({ onPick, busy, error }: { onPick: (l: Lang) => void; busy: boolean; error: string | null }) {
  useEffect(() => {
    document.documentElement.classList.remove("dark", "kiosk-large");
  }, []);
  return (
    <main className="force-light kiosk-root flex min-h-dvh flex-col bg-paper px-6 py-8 text-ink">
      <p className="flex items-center gap-3 text-k-body font-semibold text-teal">
        <span className="inline-flex size-11 items-center justify-center rounded-field bg-teal text-on-teal" aria-hidden>
          <svg viewBox="0 0 32 32" className="size-7" fill="currentColor"><path d="M13 7h6v6h6v6h-6v6h-6v-6H7v-6h6z" /></svg>
        </span>
        {LANGS.map((l) => t("appName", l)).join(" / ")}
      </p>
      <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center">
        <h1 className="flex flex-col gap-1">
          {LANGS.map((l, i) => (
            <span key={l} lang={l} className={i === 0 ? "text-k-hero font-bold" : "text-k-lead font-semibold text-muted"}>
              {t("chooseLanguage", l)}
            </span>
          ))}
        </h1>
        <div className="mt-10 grid gap-5">
          {LANGS.map((l) => (
            <button
              key={l}
              type="button"
              lang={l}
              disabled={busy}
              onClick={() => onPick(l)}
              className="group flex min-h-32 items-center justify-between gap-4 rounded-tile border-2 border-b-[6px] border-line-strong bg-surface px-8 text-left hover:border-teal transition-transform duration-(--dur-feedback) active:translate-y-[3px] active:border-b-2 disabled:opacity-60"
            >
              <span className="text-[3.25rem] leading-tight font-bold">{LANG_NAMES[l]}</span>
              <span className="text-k-body text-muted">{t("languageHint", l)}</span>
            </button>
          ))}
        </div>
        {error && (
          <p role="alert" className="mt-6 rounded-tile border-2 border-red bg-red-tint px-5 py-4 text-k-body font-semibold">
            {error}
          </p>
        )}
      </div>
    </main>
  );
}

// ---------------------------------------------------------------- question
function QuestionScreen({ s, dir, lang, busy, regions, onConsent, onAnswer, onBodyMap, onSkip, onRestart }: {
  s: KioskScreen; dir: "fwd" | "back"; lang: Lang; busy: boolean; regions: ReturnType<typeof useBodyRegions>["data"];
  onConsent: (c: "agree" | "decline") => void; onAnswer: (v: unknown) => void; onBodyMap: (b: { regions?: string[]; view?: "front" | "back"; inputMode?: "map" | "list"; special?: string }) => void;
  onSkip: () => void; onRestart: () => void;
}) {
  if (s.stage === "declined")
    return (
      <section className="flex flex-col gap-6">
        <p className="text-k-lead">{t("declined", lang)}</p>
        <Button size="kiosk" variant="primary" icon={RotateCcw} onClick={onRestart}>
          {t("startOver", lang)}
        </Button>
      </section>
    );
  if (s.stage === "done")
    return (
      <section className="flex flex-col gap-6">
        <p className="text-k-lead">{t("wait", lang)}</p>
        <Button size="kiosk" variant="primary" onClick={onRestart}>
          {t("done", lang)}
        </Button>
      </section>
    );
  const n = s.node!;
  const consent = s.stage === "consent";
  const specials = n.type === "body_map" ? n.options : [];
  const unsureOpt = n.type === "yes_no_unsure" ? n.options.find((o) => o.id === UNSURE) : undefined;
  const tiles = n.type === "yes_no_unsure" ? n.options.filter((o) => o.id !== UNSURE) : n.options;
  const showUnsure = !consent && n.type !== "body_map";
  const unsureValue = n.type === "multi_choice" ? [UNSURE] : UNSURE;
  const answer = (
    <>
      {consent && <ChoiceTiles options={n.options} value={s.value} lang={lang} busy={busy} onPick={(id) => onConsent(id as "agree" | "decline")} />}
      {!consent && (n.type === "single_choice" || n.type === "yes_no_unsure") && <ChoiceTiles options={tiles} value={s.value} lang={lang} busy={busy} onPick={onAnswer} />}
      {n.type === "multi_choice" && <MultiTiles options={n.options} value={s.value} lang={lang} busy={busy} onSubmit={onAnswer} />}
      {n.type === "number" && <Keypad min={n.min ?? 0} max={n.max ?? 999} value={s.value} lang={lang} busy={busy} onSubmit={onAnswer} />}
      {n.type === "scale_0_10" && <Scale value={s.value} lang={lang} busy={busy} onPick={onAnswer} />}
      {n.type === "free_text" && <FreeText value={s.value} lang={lang} busy={busy} onSubmit={onAnswer} />}
      {n.type === "body_map" && regions && <BodyMap catalog={regions} maxSelections={n.maxSelections ?? 3} value={s.value} lang={lang} busy={busy} onSubmit={(b) => onBodyMap(b)} />}
    </>
  );
  const wide = n.type !== "body_map" && !consent;
  return (
    <section
      data-testid="kiosk-question"
      data-node={n.id}
      data-type={consent ? "consent" : n.type}
      className={cn("flex flex-col gap-6", dir === "back" ? "animate-slide-back" : "animate-slide-fwd")}
      aria-labelledby="q-text"
    >
      {s.redFlagMessage && !consent && (
        <p className="flex items-center gap-4 rounded-tile border-2 border-on-marigold/30 bg-marigold-tint px-5 py-4 text-k-tile font-semibold" role="status">
          <Hand size={34} aria-hidden className="shrink-0" />
          {s.redFlagMessage}
        </p>
      )}
      <div className={cn("grid gap-6", wide && "landscape:lg:grid-cols-[minmax(0,9fr)_minmax(0,11fr)] landscape:lg:items-start")}>
        <h1 id="q-text" className={cn(consent ? "text-k-lead font-normal leading-normal" : "text-k-question font-bold")}>
          {n.text}
        </h1>
        <div className="flex flex-col gap-4">{answer}</div>
      </div>
      {!consent && (
        <div className="mt-2 flex flex-wrap gap-3 border-t-2 border-dashed border-line pt-5">
          {showUnsure && (
            <Button size="kiosk" disabled={busy} onClick={() => onAnswer(unsureOpt ? unsureOpt.id : unsureValue)} data-testid="unsure">
              {unsureOpt?.label ?? t("unsure", lang)}
            </Button>
          )}
          {specials.map((o) => (
            <Button key={o.id} size="kiosk" disabled={busy} onClick={() => onBodyMap({ special: o.id })} data-testid={`special-${o.id}`}>
              {o.label}
            </Button>
          ))}
          <Button size="kiosk" variant="ghost" disabled={busy} onClick={onSkip} className="ml-auto" data-testid="skip">
            {t("skip", lang)}
          </Button>
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- review
function Review({ items, lang, onEdit, onConfirm }: { items: ReviewItem[]; lang: Lang; onEdit: (nodeId: string) => void; onConfirm: () => void }) {
  return (
    <section className="animate-slide-fwd flex flex-col gap-5" aria-labelledby="rv-h" data-testid="kiosk-review">
      <h1 id="rv-h" className="text-k-question font-bold">
        {t("review", lang)}
      </h1>
      <ul className="divide-y-2 divide-line rounded-tile border-2 border-line bg-surface">
        {items.map((it) => (
          <li key={it.nodeId} className="flex items-center gap-4 px-5 py-4">
            <div className="min-w-0 flex-1">
              <p className="text-k-body text-muted">{it.question}</p>
              <p className="text-k-tile font-semibold">{it.answer}</p>
            </div>
            <Button size="kiosk" icon={Pencil} onClick={() => onEdit(it.nodeId)} aria-label={`${t("change", lang)}: ${it.question}`}>
              {t("change", lang)}
            </Button>
          </li>
        ))}
      </ul>
      <div className="sticky bottom-0 -mx-1 bg-paper/95 px-1 py-3 backdrop-blur">
        <Button size="kiosk" variant="primary" block onClick={onConfirm} data-testid="confirm-all">
          {t("confirmAll", lang)}
        </Button>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- doctor
function DoctorChoice({ doctors, lang, busy, onPick }: { doctors: DoctorOut[]; lang: Lang; busy: boolean; onPick: (id: string | null) => void }) {
  return (
    <section className="animate-slide-fwd flex flex-col gap-5" aria-labelledby="dr-h">
      <div>
        <h1 id="dr-h" className="text-k-question font-bold">
          {t("chooseDoctor", lang)}
        </h1>
        <p className="mt-2 text-k-body text-muted">{t("chooseDoctorHint", lang)}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {doctors.map((d) => (
          <Tile
            key={d.id}
            data-testid={`doctor-${d.id}`}
            selectedLabel={t("selected", lang)}
            disabled={busy}
            onClick={() => onPick(d.id)}
            sub={
              <span className="flex items-center gap-2">
                {d.lineColor && <span aria-hidden className="inline-block h-3 w-8 shrink-0 rounded-sm" style={{ background: d.lineColor, outline: d.lineColor === "#F2B33D" ? "2px solid var(--ink)" : undefined }} />}
                {d.specialty[lang] ?? d.specialty.en}
                {d.room ? `, ${t("room", lang, { room: d.room })}` : ""}
              </span>
            }
          >
            {d.name}
          </Tile>
        ))}
        <Tile data-testid="doctor-any" selectedLabel={t("selected", lang)} disabled={busy} onClick={() => onPick(null)} className="sm:col-span-2">
          {t("anyDoctor", lang)}
        </Tile>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- token slip
function SlipScreen({ stage, lang, onRetry, onDone }: { stage: Extract<Stage, { kind: "slip" }>; lang: Lang; onRetry: () => void; onDone: () => void }) {
  const [left, setLeft] = useState(SLIP_RESET_S);
  useEffect(() => {
    if (!stage.slip) return;
    const id = window.setInterval(() => setLeft((s) => s - 1), 1000);
    return () => window.clearInterval(id);
  }, [stage.slip]);
  useEffect(() => {
    if (left <= 0) onDone();
  }, [left, onDone]);
  if (stage.error)
    return (
      <section role="alert" className="flex flex-col gap-5 rounded-tile border-2 border-red bg-red-tint p-6" data-testid="slip-error">
        <p className="text-k-lead font-bold">{stage.error}</p>
        <Button size="kiosk" variant="primary" icon={RotateCcw} onClick={onRetry}>
          {t("retry", lang)}
        </Button>
      </section>
    );
  if (!stage.slip)
    return (
      <section aria-busy className="flex flex-col items-center gap-4 py-10">
        <p className="text-k-lead" role="status">
          {t("finishing", lang)}…
        </p>
        <div className="h-[34rem] w-full max-w-md animate-pulse rounded-slip bg-tint" />
      </section>
    );
  return (
    <section className="flex flex-col items-center gap-6" aria-labelledby="slip-h">
      <h1 id="slip-h" className="text-k-question font-bold" data-testid="registered">
        {t("registered", lang)}
      </h1>
      <div className="slip-counter w-full max-w-lg rounded-tile px-4 py-6">
        <TokenSlip slip={stage.slip} lang={lang} stamped />
      </div>
      <WayStrip slip={stage.slip} lang={lang} />
      <p className="text-k-body text-muted">{t("wait", lang)}</p>
      <div className="grid w-full max-w-lg gap-3 sm:grid-cols-2 no-print">
        <Button size="kiosk" icon={Printer} onClick={() => window.print()}>
          {t("print", lang)}
        </Button>
        <Button size="kiosk" variant="primary" onClick={onDone} data-testid="done">
          {t("done", lang)}
        </Button>
      </div>
      <p className="text-k-body text-muted tabular no-print" aria-live="off">
        {t("autoReset", lang, { s: left })}
      </p>
    </section>
  );
}
