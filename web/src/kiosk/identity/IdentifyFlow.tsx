import { useEffect, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, ArrowLeft, Check, ClipboardList, Eye, EyeOff, HandHelping, IdCard, Lock, Smartphone, Stethoscope, Trash2, Users } from "lucide-react";
import { ApiError, type IdentityOut, type KioskScreen } from "../../api/client";
import { Button } from "../../components/Button";
import { t, type Key, type Lang } from "../../i18n/i18n";
import { cn } from "../../lib/cn";
import { identityApi, type IdKind } from "../kioskApi";
import { NumberPad } from "./NumberPad";
import { checkIdentifier, PIN_LENGTH, PIN_START, pinConfirmed, pinStep, popDigit, pushDigit, pushPin, slots, type PinPhase } from "./validation";

export type IdentifyResult = { identity: IdentityOut | null; screen: KioskScreen | null };

type State =
  | { s: "method" }
  | { s: "number"; kind: IdKind; digits: string }
  | { s: "pin"; kind: IdKind; digits: string; mode: "login"; pin: string; error: string | null }
  | { s: "pin"; kind: IdKind; digits: string; mode: "new"; flow: PinPhase }
  | { s: "consent"; kind: IdKind; digits: string; pin: string }
  | { s: "welcome"; identity: IdentityOut; screen: KioskScreen }
  | { s: "staff"; identity: IdentityOut; screen: KioskScreen };

const ERR: Record<string, Key> = { locked: "pinLocked", not_found: "idNotFound", rate_limited: "rateLimited", mobile_format: "mobileBad", abha_format: "abhaBad" };

/**
 * Kiosk step 1: how the patient says who they are. One decision per screen: method, number, PIN, consent. Identifier + 4-digit PIN
 * (no SMS offline, so no OTP). Nothing is stored before "I agree"; "No thanks" continues as an anonymous walk-in.
 */
export function IdentifyFlow({ lang, bind, onDone, onExit, onHelp, onPrompt, onSession }: {
  lang: Lang;
  bind: (identityToken: string) => Promise<KioskScreen>;
  onDone: (r: IdentifyResult) => void;
  onExit: () => void;
  onHelp: () => void;
  onPrompt: (text: string) => void;
  onSession: (identityToken: string, masked: string) => void;
}) {
  const [st, setSt] = useState<State>({ s: "method" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLHeadingElement>(null);

  const fail = (e: unknown) => {
    if (e instanceof ApiError && e.code && ERR[e.code]) setError(t(ERR[e.code], lang));
    else setError(t("error", lang));
  };
  const attempt = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  // ---- spoken prompt per screen (read aloud only with a local voice; the header's "Listen again" repeats it)
  const prompt = (() => {
    switch (st.s) {
      case "method": return t("idTitleMethod", lang);
      case "number": return t(st.kind === "mobile" ? "idMobileTitle" : "idAbhaTitle", lang);
      case "pin": return st.mode === "login" ? t("pinEnterTitle", lang) : `${t(st.flow.phase === "choose" ? "pinNewTitle" : "pinAgainTitle", lang)}. ${t("pinNewHint", lang)}`;
      case "consent": return [t("consentTitle", lang), t("consentWhat", lang), t("consentWho", lang), t("consentWhy", lang), t("consentWithdraw", lang)].join(". ");
      case "welcome": return `${t("welcomeBack", lang)}. ${st.identity.masked}`;
      case "staff": return t("staffWillHelp", lang);
    }
  })();
  const key = st.s === "pin" ? `${st.s}-${st.mode}-${st.mode === "new" ? st.flow.phase : ""}` : st.s;
  useEffect(() => {
    onPrompt(prompt);
    window.scrollTo(0, 0);
    ref.current?.focus({ preventScroll: true });
  }, [key, lang]); // eslint-disable-line react-hooks/exhaustive-deps

  const back = () => {
    setError(null);
    if (st.s === "method") return onExit();
    if (st.s === "number") return setSt({ s: "method" });
    if (st.s === "pin") return setSt({ s: "number", kind: st.kind, digits: st.digits });
    if (st.s === "consent") return setSt({ s: "pin", kind: st.kind, digits: st.digits, mode: "new", flow: PIN_START });
    onExit();
  };

  const finish = (identity: IdentityOut) =>
    attempt(async () => {
      onSession(identity.identityToken, identity.masked);
      const screen = await bind(identity.identityToken);
      setSt({ s: "welcome", identity, screen });
    });

  const askStaff = () =>
    attempt(async () => {
      const identity = await identityApi.walkIn(lang);
      onSession(identity.identityToken, identity.masked);
      const screen = await bind(identity.identityToken);
      setSt({ s: "staff", identity, screen });
    });

  const submitNumber = (kind: IdKind, digits: string) =>
    attempt(async () => {
      const r = await identityApi.identify(kind, digits);
      setSt(r.exists ? { s: "pin", kind, digits, mode: "login", pin: "", error: null } : { s: "pin", kind, digits, mode: "new", flow: PIN_START });
    });

  const submitLogin = (kind: IdKind, digits: string, pin: string) =>
    attempt(async () => {
      try {
        await finish(await identityApi.login(kind, digits, pin));
      } catch (e) {
        if (e instanceof ApiError && e.code === "wrong_pin") {
          setSt({ s: "pin", kind, digits, mode: "login", pin: "", error: t("pinWrong", lang, { n: e.attemptsLeft ?? 0 }) });
          return;
        }
        throw e;
      }
    });

  const register = (kind: IdKind, digits: string, pin: string) =>
    attempt(async () => {
      const identity = await identityApi.register(kind, digits, pin, lang);
      onSession(identity.identityToken, identity.masked);
      const screen = await bind(identity.identityToken);
      onDone({ identity, screen });
    });

  const body = (): ReactNode => {
    if (st.s === "method")
      return (
        <div className="grid gap-5 portrait:gap-6" data-testid="id-method">
          <MethodTile icon={Smartphone} label={t("idMobile", lang)} onClick={() => setSt({ s: "number", kind: "mobile", digits: "" })} testId="id-mobile" />
          <MethodTile icon={IdCard} label={t("idAbha", lang)} onClick={() => setSt({ s: "number", kind: "abha", digits: "" })} testId="id-abha" />
          <MethodTile icon={HandHelping} label={t("idStaff", lang)} onClick={askStaff} testId="id-staff" quiet disabled={busy} />
        </div>
      );
    if (st.s === "number") {
      const fb = checkIdentifier(st.kind, st.digits);
      const g = slots(st.kind, st.digits);
      return (
        <div className="flex flex-col gap-5" data-testid="id-number">
          <div role="group" aria-label={t("idEntered", lang)} className="flex flex-wrap gap-x-4 gap-y-3" data-testid="id-digits" data-value={st.digits}>
            {g.map((grp, gi) => (
              <div key={gi} className="flex gap-1.5">
                {grp.map((d, i) => (
                  <span key={i} className={cn("flex h-14 w-7 items-center justify-center rounded-field border-2 text-2xl font-bold tabular min-[480px]:h-16 min-[480px]:w-10 min-[640px]:w-12 min-[640px]:text-3xl", d ? "border-teal bg-tint" : "border-line-strong bg-surface")}>
                    {d}
                  </span>
                ))}
              </div>
            ))}
          </div>
          <p role="status" className={cn("flex items-start gap-2 text-k-body font-semibold", fb.state === "bad" ? "text-red" : fb.state === "ok" ? "text-green" : "text-muted")} data-testid="id-feedback" data-state={fb.state}>
            {fb.state === "bad" ? <AlertTriangle size={26} aria-hidden className="mt-0.5 shrink-0" /> : fb.state === "ok" ? <Check size={26} strokeWidth={3} aria-hidden className="mt-0.5 shrink-0" /> : null}
            <span>{fb.state === "bad" ? t(fb.reason === "abha" ? "abhaBad" : "mobileBad", lang) : fb.state === "ok" ? t("digitsOk", lang) : t("digitsLeft", lang, { n: fb.remaining })}</span>
          </p>
          {st.kind === "abha" && <p className="text-k-body text-muted">{t("abhaNote", lang)}</p>}
          <NumberPad lang={lang} disabled={busy} onDigit={(d) => setSt({ ...st, digits: pushDigit(st.kind, st.digits, d) })} onDelete={() => setSt({ ...st, digits: popDigit(st.digits) })} />
          <Button size="kiosk" variant="primary" icon={Check} block disabled={fb.state !== "ok"} loading={busy} onClick={() => submitNumber(st.kind, st.digits)} data-testid="continue">
            {t("continue", lang)}
          </Button>
        </div>
      );
    }
    if (st.s === "pin") {
      const entry = st.mode === "login" ? st.pin : st.flow.entry;
      const onDigit = (d: string) => {
        if (st.mode === "login") {
          const pin = pushPin(st.pin, d);
          if (pin.length === PIN_LENGTH) submitLogin(st.kind, st.digits, pin);
          else setSt({ ...st, pin, error: null });
        } else {
          const flow = pinStep(st.flow, { digit: d });
          if (pinConfirmed(flow)) setSt({ s: "consent", kind: st.kind, digits: st.digits, pin: flow.entry });
          else setSt({ ...st, flow });
        }
      };
      const onDelete = () => (st.mode === "login" ? setSt({ ...st, pin: popDigit(st.pin) }) : setSt({ ...st, flow: pinStep(st.flow, { delete: true }) }));
      return (
        <div className="flex flex-col gap-5" data-testid={st.mode === "login" ? "id-pin-login" : "id-pin-new"}>
          {st.mode === "new" && <p className="text-k-body text-muted">{t("pinNewHint", lang)}</p>}
          <PinDots value={entry} lang={lang} />
          {st.mode === "new" && st.flow.mismatch && <Alert text={t("pinMismatch", lang)} />}
          {st.mode === "login" && st.error && <Alert text={st.error} />}
          <NumberPad lang={lang} disabled={busy} onDigit={onDigit} onDelete={onDelete} />
          {st.mode === "login" && (
            <Button size="kiosk" variant="ghost" icon={HandHelping} onClick={onHelp} data-testid="pin-forgot">
              {t("pinForgot", lang)}
            </Button>
          )}
        </div>
      );
    }
    if (st.s === "consent")
      return (
        <div className="flex flex-col gap-5" data-testid="id-consent">
          <ul className="flex flex-col gap-5 rounded-tile border-2 border-line bg-surface p-5 portrait:gap-7 portrait:p-7">
            <ConsentLine icon={ClipboardList} text={t("consentWhat", lang)} />
            <ConsentLine icon={Users} text={t("consentWho", lang)} />
            <ConsentLine icon={Stethoscope} text={t("consentWhy", lang)} />
            <ConsentLine icon={Trash2} text={t("consentWithdraw", lang)} />
          </ul>
          <Button size="kiosk" variant="primary" icon={Check} block loading={busy} onClick={() => register(st.kind, st.digits, st.pin)} data-testid="consent-agree">
            {t("consentAgree", lang)}
          </Button>
          <Button size="kiosk" variant="ghost" block disabled={busy} onClick={() => onDone({ identity: null, screen: null })} data-testid="consent-no">
            {t("consentNo", lang)}
          </Button>
        </div>
      );
    if (st.s === "welcome")
      return (
        <div className="flex flex-col gap-5" data-testid="id-welcome">
          <p className="text-k-lead font-bold tabular">{st.identity.masked}</p>
          {st.identity.lastVisit && <p className="text-k-body text-muted">{t("lastVisit", lang, { date: new Date(`${st.identity.lastVisit}T00:00:00`).toLocaleDateString(`${lang}-IN-u-nu-latn`, { day: "numeric", month: "short", year: "numeric" }) })}</p>}
          <Button size="kiosk" variant="primary" icon={Check} block onClick={() => onDone({ identity: st.identity, screen: st.screen })} data-testid="continue">
            {t("continue", lang)}
          </Button>
        </div>
      );
    return (
      <div className="flex flex-col gap-5" data-testid="id-staff-note">
        <Button size="kiosk" variant="primary" icon={Check} block onClick={() => onDone({ identity: st.identity, screen: st.screen })} data-testid="continue">
          {t("continue", lang)}
        </Button>
      </div>
    );
  };

  const title =
    st.s === "method" ? t("idTitleMethod", lang)
    : st.s === "number" ? t(st.kind === "mobile" ? "idMobileTitle" : "idAbhaTitle", lang)
    : st.s === "pin" ? (st.mode === "login" ? t("pinEnterTitle", lang) : t(st.flow.phase === "choose" ? "pinNewTitle" : "pinAgainTitle", lang))
    : st.s === "consent" ? t("consentTitle", lang)
    : st.s === "welcome" ? t("welcomeBack", lang)
    : t("staffWillHelp", lang);

  return (
    <section className="animate-slide-fwd mx-auto flex w-full max-w-2xl flex-col gap-6" aria-labelledby="id-h" data-testid="identify" data-screen={st.s}>
      {st.s !== "welcome" && st.s !== "staff" && (
        <div>
          <Button size="kiosk" icon={ArrowLeft} onClick={back} disabled={busy} data-testid="id-back">
            {t("back", lang)}
          </Button>
        </div>
      )}
      <h1 id="id-h" ref={ref} tabIndex={-1} className={cn("text-k-question font-bold outline-none", st.s === "staff" && "text-k-lead")}>
        {title}
      </h1>
      {error && <Alert text={error} />}
      {body()}
    </section>
  );
}

function MethodTile({ icon: Icon, label, onClick, testId, quiet, disabled }: { icon: typeof Smartphone; label: string; onClick: () => void; testId: string; quiet?: boolean; disabled?: boolean }) {
  return (
    <button
      type="button"
      data-testid={testId}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "flex min-h-28 items-center gap-5 rounded-tile border-2 border-b-[6px] px-6 portrait:min-h-44 portrait:gap-6 text-left transition-transform duration-(--dur-feedback) active:translate-y-[3px] active:border-b-2 disabled:opacity-60",
        quiet ? "border-line-strong bg-paper" : "border-line-strong bg-surface hover:border-teal",
      )}
    >
      <span className={cn("flex size-16 shrink-0 items-center justify-center rounded-tile portrait:size-24", quiet ? "bg-tint text-ink" : "bg-teal text-on-teal")} aria-hidden>
        <Icon size={40} strokeWidth={2} />
      </span>
      <span className="text-k-tile font-bold leading-snug">{label}</span>
    </button>
  );
}

function ConsentLine({ icon: Icon, text }: { icon: typeof Lock; text: string }) {
  return (
    <li className="flex items-start gap-4">
      <span className="flex size-12 shrink-0 items-center justify-center rounded-tile bg-tint text-teal" aria-hidden>
        <Icon size={28} />
      </span>
      <span className="pt-1 text-k-tile leading-snug">{text}</span>
    </li>
  );
}

function Alert({ text }: { text: string }) {
  return (
    <p role="alert" className="flex items-start gap-3 rounded-tile border-2 border-red bg-red-tint px-5 py-4 text-k-body font-semibold" data-testid="id-alert">
      <AlertTriangle size={28} aria-hidden className="mt-0.5 shrink-0 text-red" />
      {text}
    </p>
  );
}

function PinDots({ value, lang }: { value: string; lang: Lang }) {
  const [show, setShow] = useState(false);
  return (
    <div className="flex items-center gap-4">
      <div className="flex flex-1 justify-center gap-4" data-testid="pin-dots" data-filled={value.length} role="img" aria-label={`${value.length} / ${PIN_LENGTH}`}>
        {Array.from({ length: PIN_LENGTH }, (_, i) => (
          <span key={i} className={cn("flex size-16 items-center justify-center rounded-full border-2 text-3xl font-bold tabular", i < value.length ? "border-teal bg-tint" : "border-line-strong bg-surface")}>
            {i < value.length ? (show ? value[i] : <span className="size-5 rounded-full bg-ink" />) : null}
          </span>
        ))}
      </div>
      <Button size="kiosk" icon={show ? EyeOff : Eye} onClick={() => setShow((s) => !s)} aria-pressed={show} aria-label={t(show ? "pinHide" : "pinShow", lang)} className="px-4" data-testid="pin-toggle">
        <span className="hidden sm:inline">{t(show ? "pinHide" : "pinShow", lang)}</span>
      </Button>
    </div>
  );
}
