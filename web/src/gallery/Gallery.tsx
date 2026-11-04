import { useEffect, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Bell, Check, CircleHelp, Plus, Printer, Save, Volume2, X } from "lucide-react";
import { get, type Card, type RedFlag, type SystemConfig, type TokenSlip as Slip } from "../api/client";
import { Button, DangerButton, IconButton, SuccessButton, ToggleButton } from "../components/Button";
import { ChainSeal, HashLink } from "../components/AuditChain";
import { RedFlagRow } from "../components/RedFlagRow";
import { Tile } from "../components/Tile";
import { TokenSlip } from "../components/TokenSlip";
import { Checkbox, Chip, DemoBar, EmptyState, ErrorState, Notice, Pill, PrototypeBanner, SelectField, Skeleton, TextArea, TextField } from "../components/ui";
import { DoseRuler } from "../dosing/DoseRuler";
import { ResultCard } from "../dosing/ResultCard";
import { asResult } from "../dosing/types";
import { LANG_NAMES, LANGS, t, type Lang } from "../i18n/i18n";
import { applyTheme } from "../shell/theme";
import samples from "./samples.json";

type Sample = { result: unknown; card: Card };
const S = samples as unknown as Record<"ok" | "needs_input" | "blocked" | "refused" | "override", Sample> & { redFlags: RedFlag[] };

const SLIP: Slip = {
  queueNumber: 27, queueDate: "2026-11-04", token: "PT-7KQ2MD", room: "12", floor: { en: "Ground floor", hi: "भूतल", mr: "तळमजला" },
  guidance: "follow_line", estimatedWaitMinutes: 20, patientsAhead: 2, estimateLabel: "estimate", papersAdded: 0, identifierMasked: null,
  doctor: { id: "dr_general", name: "Dr. Asha Kulkarni", specialty: { en: "General Physician", hi: "सामान्य चिकित्सक", mr: "सामान्य वैद्य" }, room: "12",
    floor: { en: "Ground floor", hi: "भूतल", mr: "तळमजला" }, lineColor: "#1E7B45", lineName: { en: "green", hi: "हरी", mr: "हिरव्या" }, lineTextColor: "#FFFFFF" },
};

function Section({ id, title, children, note }: { id: string; title: string; children: ReactNode; note?: string }) {
  return (
    <section id={id} className="border-t border-line py-8" aria-labelledby={`${id}-h`}>
      <h2 id={`${id}-h`} className="text-lg font-semibold">
        {title}
      </h2>
      {note && <p className="mt-1 max-w-prose text-sm text-muted">{note}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

/** Every component in every state, for review and the pitch. Dev builds and DEMO_MODE only. ?lang=hi&theme=dark */
export default function Gallery() {
  const [params, setParams] = useSearchParams();
  const lang = (LANGS.includes(params.get("lang") as Lang) ? params.get("lang") : "en") as Lang;
  const theme = params.get("theme") === "dark" ? "dark" : "light";
  const cfg = useQuery({ queryKey: ["config"], queryFn: () => get<SystemConfig>("/api/system/config") });
  const [toggle, setToggle] = useState(true);
  const [sel, setSel] = useState<string | null>("b");
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);
  const allowed = import.meta.env.DEV || cfg.data?.demoMode;
  if (!allowed)
    return (
      <main className="p-6">
        <Notice title="The gallery is for development and demo mode">Start the server with DEMO_MODE=1 to see it.</Notice>
      </main>
    );
  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    p.set(k, v);
    setParams(p, { replace: true });
  };
  return (
    <div className="min-h-dvh bg-paper text-ink">
      <header className="sticky top-0 z-30 flex flex-wrap items-center gap-3 border-b border-line bg-paper/95 px-6 py-3 backdrop-blur">
        <h1 className="mr-auto text-xl font-bold">Component gallery</h1>
        <div role="radiogroup" aria-label="Language" className="flex gap-1">
          {LANGS.map((l) => (
            <Button key={l} size="sm" variant={l === lang ? "primary" : "secondary"} role="radio" aria-checked={l === lang} onClick={() => set("lang", l)}>
              {LANG_NAMES[l]}
            </Button>
          ))}
        </div>
        <div role="radiogroup" aria-label="Theme" className="flex gap-1">
          {(["light", "dark"] as const).map((th) => (
            <Button key={th} size="sm" variant={th === theme ? "primary" : "secondary"} role="radio" aria-checked={th === theme} onClick={() => set("theme", th)}>
              {th === "light" ? "Light" : "Dark"}
            </Button>
          ))}
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 pb-20" lang={lang}>
        <Section id="buttons" title="Buttons" note="Eight variants. Loading keeps its width; icon-only buttons require a label; danger asks once more.">
          <div className="flex flex-wrap items-start gap-3">
            <Button variant="primary" icon={Save}>Save vitals</Button>
            <Button>Cancel</Button>
            <Button variant="ghost" icon={Plus}>Add a medicine</Button>
            <DangerButton confirmLabel="Discard scan now" onConfirm={() => undefined}>Discard scan</DangerButton>
            <Button variant="primary" loading>Run dosage check</Button>
            <SuccessButton>Saved</SuccessButton>
            <IconButton icon={Bell} label="Mute alert sound" variant="secondary" />
            <ToggleButton pressed={toggle} onPressedChange={setToggle} icon={Volume2}>
              Sound {toggle ? "on" : "off"}
            </ToggleButton>
            <Button variant="primary" disabled>Confirm and save to record</Button>
          </div>
          <div className="force-light mt-6 flex flex-wrap items-start gap-3 rounded-panel bg-paper p-4 text-ink">
            <Button size="kiosk" variant="primary" icon={Check}>{t("continue", lang)}</Button>
            <Button size="kiosk">{t("unsure", lang)}</Button>
            <Button size="kiosk" variant="ghost">{t("skip", lang)}</Button>
            <Button size="kiosk" icon={ArrowLeft}>{t("back", lang)}</Button>
            <IconButton size="kiosk" icon={CircleHelp} label={t("help", lang)} variant="secondary" />
            <Button size="kiosk" icon={Printer}>{t("print", lang)}</Button>
          </div>
        </Section>

        <Section id="tiles" title="Kiosk tiles" note="Default, selected (check icon and word), disabled. The kiosk is always light.">
          <div className="force-light grid gap-3 rounded-panel bg-paper p-4 text-ink sm:grid-cols-2">
            {[
              ["a", { en: "Today", hi: "आज", mr: "आज" }],
              ["b", { en: "1 to 3 days", hi: "1 से 3 दिन", mr: "1 ते 3 दिवस" }],
              ["c", { en: "4 to 7 days", hi: "4 से 7 दिन", mr: "4 ते 7 दिवस" }],
              ["d", { en: "More than a week, and it keeps coming back", hi: "एक हफ्ते से ज़्यादा, और बार-बार लौटता है", mr: "एका आठवड्यापेक्षा जास्त, आणि पुन्हा पुन्हा येते" }],
            ].map(([id, label]) => (
              <Tile key={id as string} selected={sel === id} selectedLabel={t("selected", lang)} onClick={() => setSel(id as string)}>
                {(label as Record<Lang, string>)[lang]}
              </Tile>
            ))}
            <Tile selectedLabel={t("selected", lang)} disabled>
              {lang === "en" ? "Not available" : lang === "hi" ? "उपलब्ध नहीं" : "उपलब्ध नाही"}
            </Tile>
          </div>
          <div className="force-light mt-4 flex flex-wrap gap-2 rounded-panel bg-paper p-4 text-ink">
            <Chip onRemove={() => undefined} removeLabel={t("remove", lang, { x: "Chest" })}>{lang === "en" ? "Chest centre" : lang === "hi" ? "छाती का बीच" : "छातीचा मध्य"}</Chip>
            <Chip onRemove={() => undefined} removeLabel={t("remove", lang, { x: "arm" })}>{lang === "en" ? "Left upper arm" : lang === "hi" ? "बायाँ ऊपरी हाथ" : "डावा वरचा हात"}</Chip>
          </div>
        </Section>

        <Section id="inputs" title="Inputs" note="Errors say what happened and how to fix it; they are announced and the first one gets focus.">
          <div className="grid max-w-3xl gap-4 sm:grid-cols-2">
            <TextField label="BP systolic" suffix="mmHg" inputMode="numeric" defaultValue="320" error="Enter a value from 40 to 300." />
            <TextField label="Pulse" suffix="/min" inputMode="numeric" defaultValue="88" help="Measured at rest." />
            <SelectField label="Reason category" error="Choose a reason category." defaultValue="">
              <option value="">Choose…</option>
              <option>Benefit outweighs risk</option>
            </SelectField>
            <TextArea label="Written reason (at least 10 characters)" defaultValue="short" error="Write a reason of at least 10 characters." />
            <Checkbox label="Weight reported by patient is correct" defaultChecked />
            <Checkbox label="I have checked these" />
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Pill tone="red">Urgent</Pill>
            <Pill tone="green">Vitals</Pill>
            <Pill tone="marigold">2 scans to confirm</Pill>
            <Pill tone="teal">In progress</Pill>
            <Pill>Complete</Pill>
          </div>
        </Section>

        <Section id="banners" title="Banners and notices">
          <div className="flex max-w-3xl flex-col gap-3">
            <PrototypeBanner />
            <DemoBar text="DEMO - UNVERIFIED DATA" />
            <Notice tone="ok" title="Vitals saved">The doctor can see them now.</Notice>
            <Notice tone="warn" title="Outside the usual adult range (draft thresholds)">BP systolic high, pulse fast.</Notice>
            <Notice tone="stop" title="Scanning is unavailable">The local model server (Ollama) is not running on this computer. Start it with ollama serve.</Notice>
            <Notice>Answers are saved as doctor-confirmed for this visit and reused for every drug checked.</Notice>
          </div>
        </Section>

        <Section id="results" title="Dosage check results" note="Real engine output for the synthetic demo patients. No dose number appears unless the status is ok.">
          <div className="grid gap-10">
            {(["ok", "needs_input", "blocked", "refused", "override"] as const).map((k) => (
              <div key={k}>
                <p className="mb-2 text-sm font-semibold text-muted">{k === "override" ? "ok after a recorded override" : k}</p>
                <ResultCard result={asResult(S[k].result)} card={S[k].card} />
              </div>
            ))}
          </div>
        </Section>

        <Section id="ruler" title="Dose ruler (ok only)">
          <div className="max-w-xl rounded-panel border border-line bg-surface p-4">
            <DoseRuler result={asResult(S.ok.result)} />
          </div>
        </Section>

        <Section id="redflags" title="Red-flag rows" note="Icon, severity word, staff message, draft label and the triggering answers. Never colour alone.">
          <div className="flex flex-col gap-3">
            {S.redFlags.slice(0, 2).map((f) => (
              <RedFlagRow key={f.ruleId} flag={f} token="PT-DEMO22" />
            ))}
            <RedFlagRow flag={{ ...S.redFlags[0]!, severity: "soon" }} token="PT-4XQ2ME" compact />
          </div>
        </Section>

        <Section id="slip" title="Token slip (parchi)">
          <div className="force-light slip-counter rounded-panel p-6 text-ink">
            <TokenSlip slip={SLIP} lang={lang} stamped />
          </div>
        </Section>

        <Section id="audit" title="Audit chain">
          <div className="flex flex-col items-start gap-3">
            <ChainSeal ok entries={12431} />
            <ChainSeal ok={false} entries={12431} firstBad={8812} />
            <div className="flex gap-6">
              <HashLink hash="3fa1c09be2" prev="9be04ac1" />
              <HashLink hash="77d0aa01" prev="3fa1c09b" bad />
            </div>
          </div>
        </Section>

        <Section id="states" title="Empty, loading and error states">
          <div className="grid gap-4 md:grid-cols-3">
            <EmptyState title="No patients yet today">New patients appear here as soon as they start on the kiosk.</EmptyState>
            <div className="flex flex-col gap-2 rounded-panel border border-line p-4" aria-busy="true">
              <Skeleton className="h-5 w-40" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-10 w-32" />
            </div>
            <ErrorState title="Could not load the board" message="The server did not answer. Check that the clinic computer is on." onRetry={() => undefined} />
          </div>
        </Section>
        <p className="pt-6 text-xs text-muted">
          <X size={12} className="inline" aria-hidden /> Nothing on this page is a real patient. Hindi and Marathi text is machine-drafted, needs native review.
        </p>
      </main>
    </div>
  );
}
