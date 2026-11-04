import { useEffect, useRef, useState, type ReactNode, type Ref } from "react";
import { AlertTriangle, Camera, Check, ImagePlus, Pencil, RotateCcw, Trash2, X } from "lucide-react";
import { ApiError, type ScanField, type ScanMedicine, type ScanOut } from "../../api/client";
import { Button } from "../../components/Button";
import { t, type Key, type Lang } from "../../i18n/i18n";
import { cn } from "../../lib/cn";
import type { kioskClient } from "../kioskApi";

type Client = ReturnType<typeof kioskClient>;
type Notice = "dark" | "blurry" | "unreadable_file" | "too_big" | "error" | null;
const RUNNING = new Set(["queued", "preparing", "reading", "structuring"]);
const STAGE: Record<string, Key> = { queued: "stageQueued", preparing: "stagePreparing", reading: "stageReading", structuring: "stageStructuring" };
const TYPE: Record<string, Key> = { prescription: "typePrescription", lab_report: "typeLab", other: "typeOther" };

/**
 * Kiosk step 2: scan old papers. The camera (or a picture from the device) goes to the local reader; the patient checks what it
 * read and says "This is right". Everything shown is what the camera read, not a fact: the doctor decides what to use.
 * Never blocks: skip, type it, or ask staff at every point. No medical meaning is shown here, only the words on the paper.
 */
export function ScanStep({ client, lang, onNext, onSkip, onHelp, onPrompt }: {
  client: Client; lang: Lang; onNext: () => void; onSkip: () => void; onHelp: () => void; onPrompt: (text: string) => void;
}) {
  const [scans, setScans] = useState<ScanOut[]>([]);
  const [mode, setMode] = useState<"home" | "camera" | "preview">("home");
  const [shot, setShot] = useState<Blob | null>(null);
  const [blocked, setBlocked] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState(false);
  const [edit, setEdit] = useState<{ scan: ScanOut; index: number } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const confirmedCount = scans.filter((s) => s.confirmed).length;

  useEffect(() => {
    onPrompt(`${t("scanTitle", lang)}. ${t("scanLead", lang)}`);
  }, [lang]); // eslint-disable-line react-hooks/exhaustive-deps

  // real progress: poll every running job (the server reports its stage and the streamed token count)
  const running = scans.filter((s) => RUNNING.has(s.status)).map((s) => s.id).join(",");
  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => {
      running.split(",").forEach((sid) =>
        client.scans.get(sid).then((fresh) => setScans((all) => all.map((x) => (x.id === sid ? fresh : x))), () => undefined),
      );
    }, 700);
    return () => window.clearInterval(id);
  }, [running, client]);

  const send = async (blob: Blob) => {
    setBusy(true);
    setNotice(null);
    try {
      const r = await client.scans.upload(blob);
      if (r.status === "retake") setNotice(r.message === "dark" ? "dark" : "blurry");
      else if (r.status === "failed") setNotice("unreadable_file");
      else setScans((all) => [...all, r]);
      setMode("home");
      setShot(null);
    } catch (e) {
      setNotice(e instanceof ApiError && e.code === "too_big" ? "too_big" : "error");
      setMode("home");
    } finally {
      setBusy(false);
    }
  };

  const patchLocal = (fresh: ScanOut) => setScans((all) => all.map((x) => (x.id === fresh.id ? fresh : x)));
  const confirm = (s: ScanOut) => client.scans.confirm(s.id).then(patchLocal);
  const remove = (s: ScanOut) => client.scans.remove(s.id).then(() => setScans((all) => all.filter((x) => x.id !== s.id)));
  const save = (s: ScanOut, meds: ScanMedicine[]) =>
    client.scans
      .correct(s.id, { medicines: meds.map((m) => ({ name: m.name.value, dose: m.dose.value, frequency: m.frequency.value })) })
      .then((fresh) => {
        patchLocal(fresh);
        setEdit(null);
      });

  const skip = async () => {
    setBusy(true);
    await Promise.all(scans.filter((s) => !s.confirmed).map((s) => client.scans.remove(s.id).catch(() => undefined)));
    onSkip();
  };

  const pending = scans.some((s) => RUNNING.has(s.status) || !s.confirmed);
  const noticeText =
    notice === "dark" ? t("retakeDark", lang) : notice === "blurry" ? t("retakeBlurry", lang) : notice === "unreadable_file" ? t("unreadableFile", lang) : notice ? t("error", lang) : null;

  if (mode === "camera")
    return (
      <CameraView
        lang={lang}
        onShot={(b) => { setShot(b); setMode("preview"); }}
        onCancel={() => setMode("home")}
        onBlocked={() => { setBlocked(true); setMode("home"); }}
      />
    );
  if (mode === "preview" && shot)
    return <Preview blob={shot} lang={lang} busy={busy} onRetake={() => { setShot(null); setMode(blocked ? "home" : "camera"); }} onUse={() => send(shot)} />;

  return (
    <section className="animate-slide-fwd mx-auto flex w-full max-w-3xl flex-col gap-6" aria-labelledby="scan-h" data-testid="scan-step">
      <div>
        <h1 id="scan-h" className="text-k-question font-bold">{t("scanTitle", lang)}</h1>
        <p className="mt-2 text-k-body text-muted">{t("scanLead", lang)}</p>
      </div>
      <p className="text-k-lead font-bold tabular" data-testid="papers-count" role="status">{t("papersAdded", lang, { n: confirmedCount })}</p>
      {blocked && <Banner text={t("cameraBlocked", lang)} action={<Button size="kiosk" onClick={onHelp}>{t("help", lang)}</Button>} />}
      {noticeText && <Banner text={noticeText} testId="scan-notice" />}

      <div className="grid gap-3 sm:grid-cols-2">
        {!blocked && (
          <Button size="kiosk" variant={scans.length ? "secondary" : "primary"} icon={Camera} disabled={busy} onClick={() => setMode("camera")} data-testid="scan-take">
            {scans.length ? t("scanAnother", lang) : t("scanTake", lang)}
          </Button>
        )}
        <Button size="kiosk" icon={ImagePlus} disabled={busy} onClick={() => fileRef.current?.click()} data-testid="scan-upload">
          {t("scanUpload", lang)}
        </Button>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          capture="environment"
          className="sr-only"
          tabIndex={-1}
          aria-hidden
          data-testid="scan-file"
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (f) { setShot(f); setMode("preview"); }
          }}
        />
      </div>

      <ul className="flex flex-col gap-5">
        {scans.map((s) => (
          <ScanCard
            key={s.id}
            s={s}
            lang={lang}
            client={client}
            onConfirm={() => confirm(s)}
            onRemove={() => remove(s)}
            onEdit={(i) => setEdit({ scan: s, index: i })}
            onAddMed={() => setEdit({ scan: s, index: s.medicines.length })}
          />
        ))}
      </ul>

      <div className="flex flex-col gap-3 border-t-2 border-dashed border-line pt-5">
        {scans.length > 0 && (
          <Button size="kiosk" variant="primary" block disabled={pending || busy} onClick={onNext} data-testid="scan-next">
            {t("scanNext", lang)}
          </Button>
        )}
        <Button size="kiosk" variant={scans.length ? "ghost" : "secondary"} block disabled={busy} onClick={skip} data-testid="scan-skip">
          {t("scanSkip", lang)}
        </Button>
      </div>

      {edit && <RowEditor lang={lang} scan={edit.scan} index={edit.index} onClose={() => setEdit(null)} onSave={save} />}
    </section>
  );
}

// ---------------------------------------------------------------- camera
function CameraView({ lang, onShot, onCancel, onBlocked }: { lang: Lang; onShot: (b: Blob) => void; onCancel: () => void; onBlocked: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let stream: MediaStream | null = null;
    let dead = false;
    if (!navigator.mediaDevices?.getUserMedia) {
      onBlocked();
      return;
    }
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 } }, audio: false })
      .then((s) => {
        if (dead) return s.getTracks().forEach((x) => x.stop());
        stream = s;
        if (video.current) video.current.srcObject = s;
      })
      .catch(onBlocked);
    return () => {
      dead = true;
      stream?.getTracks().forEach((x) => x.stop());
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const capture = () => {
    const v = video.current;
    if (!v || !v.videoWidth) return;
    const c = document.createElement("canvas");
    const k = Math.min(1, 2000 / Math.max(v.videoWidth, v.videoHeight));
    c.width = Math.round(v.videoWidth * k);
    c.height = Math.round(v.videoHeight * k);
    c.getContext("2d")!.drawImage(v, 0, 0, c.width, c.height);
    c.toBlob((b) => b && onShot(b), "image/jpeg", 0.9);
  };
  return (
    <section className="mx-auto flex w-full max-w-3xl flex-col gap-5" aria-label={t("scanTake", lang)} data-testid="scan-camera">
      <div className="relative overflow-hidden rounded-tile bg-ink">
        <video ref={video} autoPlay playsInline muted onPlaying={() => setReady(true)} className="aspect-[3/4] max-h-[60dvh] w-full object-cover landscape:aspect-video" />
        <div className="pointer-events-none absolute inset-6 rounded-tile border-4 border-dashed border-white/90" aria-hidden />
        <p className="absolute inset-x-0 bottom-0 bg-ink/80 px-4 py-3 text-center text-k-body font-semibold text-white">{t("scanFrame", lang)}</p>
      </div>
      <div className="grid grid-cols-[1fr_2fr] gap-3">
        <Button size="kiosk" icon={X} onClick={onCancel} data-testid="camera-cancel">{t("back", lang)}</Button>
        <Button size="kiosk" variant="primary" icon={Camera} disabled={!ready} onClick={capture} data-testid="camera-capture" className="min-h-20">{t("scanCapture", lang)}</Button>
      </div>
    </section>
  );
}

function Preview({ blob, lang, busy, onRetake, onUse }: { blob: Blob; lang: Lang; busy: boolean; onRetake: () => void; onUse: () => void }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    const u = URL.createObjectURL(blob);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [blob]);
  return (
    <section className="mx-auto flex w-full max-w-3xl flex-col gap-5" aria-label={t("scanUse", lang)} data-testid="scan-preview">
      {url && <img src={url} alt="" className="max-h-[60dvh] w-full rounded-tile border-2 border-line bg-surface object-contain" />}
      <div className="grid gap-3 sm:grid-cols-2">
        <Button size="kiosk" icon={RotateCcw} disabled={busy} onClick={onRetake} data-testid="scan-retake">{t("scanRetake", lang)}</Button>
        <Button size="kiosk" variant="primary" icon={Check} loading={busy} onClick={onUse} data-testid="scan-use">{t("scanUse", lang)}</Button>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- one paper
function Thumb({ client, id, has }: { client: Client; id: string; has: boolean }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!has) return;
    let u: string | null = null;
    let dead = false;
    client.scans.image(id).then((x) => {
      if (dead && x) URL.revokeObjectURL(x);
      else { u = x; setUrl(x); }
    });
    return () => { dead = true; if (u) URL.revokeObjectURL(u); };
  }, [id, has]); // eslint-disable-line react-hooks/exhaustive-deps
  return url ? <img src={url} alt="" className="h-28 w-20 shrink-0 rounded-field border-2 border-line bg-surface object-cover" /> : <span className="h-28 w-20 shrink-0 rounded-field bg-tint" aria-hidden />;
}

function ScanCard({ s, lang, client, onConfirm, onRemove, onEdit, onAddMed }: {
  s: ScanOut; lang: Lang; client: Client; onConfirm: () => Promise<unknown>; onRemove: () => void; onEdit: (i: number) => void; onAddMed: () => void;
}) {
  const running = RUNNING.has(s.status);
  const pct = Math.round(s.progress * 100);
  const [bad, setBad] = useState(false);
  return (
    <li className={cn("flex flex-col gap-4 rounded-tile border-2 p-4", s.confirmed ? "border-green bg-green-tint" : "border-line bg-surface")} data-testid="scan-card" data-status={s.status} data-confirmed={s.confirmed}>
      <div className="flex gap-4">
        <Thumb client={client} id={s.id} has={s.hasImage} />
        <div className="min-w-0 flex-1">
          {running ? (
            <div data-testid="scan-progress">
              <p className="text-k-tile font-bold">{t("scanReading", lang)}</p>
              <p className="text-k-body text-muted" data-testid="scan-stage">{t(STAGE[s.stage] ?? "stageReading", lang)}, {t("seconds", lang, { s: Math.round(s.elapsedS) })}</p>
              <div className="mt-3 h-4 overflow-hidden rounded-full bg-tint" role="progressbar" aria-label={t("scanReading", lang)} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
                <div className="h-full bg-teal transition-[width] duration-500" style={{ width: `${pct}%` }} />
              </div>
              <p className="mt-1 text-k-body font-semibold tabular">{pct}%</p>
            </div>
          ) : s.status === "done" ? (
            <div>
              <p className="text-k-tile font-bold" data-testid="scan-type">{t(TYPE[s.docType ?? "other"] ?? "typeOther", lang)}</p>
              <p className="text-k-body text-muted tabular" data-testid="scan-date">{t("scanDate", lang)}: {s.docDate?.value ?? t("notFoundField", lang)}</p>
              {s.confirmed && (
                <p className="mt-1 flex items-center gap-2 text-k-body font-bold text-green">
                  <Check size={22} strokeWidth={3} aria-hidden />
                  {t("papersAdded", lang, { n: 1 })}
                </p>
              )}
            </div>
          ) : s.status === "unavailable" ? (
            <p className="text-k-body font-semibold">{t("modelDown", lang)}</p>
          ) : (
            <p className="text-k-body font-semibold">{t("readFailed", lang)}</p>
          )}
        </div>
      </div>

      {s.status === "done" && (
        <>
          <ul className="flex flex-col gap-2" data-testid="scan-meds">
            {s.medicines.map((m, i) => (
              <MedRow key={i} m={m} lang={lang} locked={s.confirmed} onClick={() => onEdit(i)} />
            ))}
          </ul>
          {s.freeText && <p className="whitespace-pre-line rounded-field bg-tint px-4 py-3 text-k-body" data-testid="scan-free">{s.freeText}</p>}
          {!s.confirmed && <Button size="kiosk" icon={Pencil} onClick={onAddMed} data-testid="scan-add-med">{t("addMedicine", lang)}</Button>}
          <p className="text-k-body text-muted">{t("scanNote", lang)}</p>
        </>
      )}

      {s.status === "failed" && !s.confirmed && <Button size="kiosk" icon={Pencil} onClick={onAddMed} data-testid="scan-type-it">{t("addMedicine", lang)}</Button>}

      <div className="flex flex-wrap gap-3">
        {(s.status === "done" || s.status === "unavailable") && !s.confirmed && (
          <Button size="kiosk" variant="primary" icon={Check} onClick={() => { setBad(false); onConfirm().catch(() => setBad(true)); }} data-testid="scan-confirm">
            {s.status === "unavailable" ? t("showDoctor", lang) : t("scanRight", lang)}
          </Button>
        )}
        {!running && <Button size="kiosk" variant="ghost" icon={Trash2} onClick={onRemove} data-testid="scan-remove">{t("scanRemove", lang)}</Button>}
      </div>
      {bad && <p role="alert" className="text-k-body font-semibold text-red">{t("error", lang)}</p>}
    </li>
  );
}

function Field({ f, label, big, lang }: { f: ScanField; label: string; big?: boolean; lang: Lang }) {
  return (
    <span className="block min-w-0">
      <span className="block text-base text-muted">{label}</span>
      <span className={cn("block break-words", big ? "text-k-tile font-bold" : "text-k-body font-semibold", !f.value && "font-normal text-muted")}>{f.value ?? t("notFoundField", lang)}</span>
    </span>
  );
}

function MedRow({ m, lang, locked, onClick }: { m: ScanMedicine; lang: Lang; locked: boolean; onClick: () => void }) {
  const check = m.name.check || m.dose.check || m.frequency.check;
  const inner = (
    <>
      <span className="grid flex-1 gap-2 sm:grid-cols-[2fr_1fr_1fr]">
        <Field f={m.name} label={t("medName", lang)} big lang={lang} />
        <Field f={m.dose} label={t("medDose", lang)} lang={lang} />
        <Field f={m.frequency} label={t("medFreq", lang)} lang={lang} />
      </span>
      {check && !locked && (
        <span className="flex shrink-0 items-center gap-2 self-start rounded-full border-2 border-on-marigold bg-marigold px-3 py-1 text-base font-bold text-on-marigold" data-testid="check-flag">
          <AlertTriangle size={20} aria-hidden />
          {t("scanCheck", lang)}
        </span>
      )}
      {!locked && <Pencil size={26} aria-hidden className="shrink-0 text-teal" />}
    </>
  );
  const cls = cn("flex w-full items-center gap-3 rounded-tile border-2 px-4 py-3 text-left", check && !locked ? "border-on-marigold/60 bg-marigold-tint" : "border-line bg-paper");
  return (
    <li>
      {locked ? (
        <div className={cls} data-testid="med-row">{inner}</div>
      ) : (
        <button type="button" className={cn(cls, "min-h-20 active:translate-y-px")} onClick={onClick} data-testid="med-row" data-check={check || undefined} aria-label={`${t("editRow", lang)}: ${m.name.value ?? ""}`}>
          {inner}
        </button>
      )}
    </li>
  );
}

// ---------------------------------------------------------------- correct one row
function EditField({ label, value, set, inputRef }: { label: string; value: string; set: (s: string) => void; inputRef?: Ref<HTMLInputElement> }) {
  return (
    <label className="flex flex-col gap-1 text-k-body font-semibold">
      {label}
      <input ref={inputRef} value={value} onChange={(e) => set(e.target.value)} maxLength={120} className="min-h-16 rounded-tile border-2 border-line-strong bg-surface px-4 text-k-tile font-normal" />
    </label>
  );
}

function RowEditor({ lang, scan, index, onClose, onSave }: { lang: Lang; scan: ScanOut; index: number; onClose: () => void; onSave: (s: ScanOut, meds: ScanMedicine[]) => Promise<void> }) {
  const cur = scan.medicines[index];
  const [name, setName] = useState(cur?.name.value ?? "");
  const [dose, setDose] = useState(cur?.dose.value ?? "");
  const [freq, setFreq] = useState(cur?.frequency.value ?? "");
  const [busy, setBusy] = useState(false);
  const first = useRef<HTMLInputElement>(null);
  useEffect(() => first.current?.focus(), []);
  const f = (v: string): ScanField => ({ value: v.trim() || null, confidence: null, check: false });
  const commit = (drop: boolean) => {
    const meds = scan.medicines.filter((_, i) => i !== index);
    if (!drop) meds.splice(index, 0, { name: f(name), dose: f(dose), frequency: f(freq) });
    setBusy(true);
    onSave(scan, meds).finally(() => setBusy(false));
  };
  return (
    <div className="fixed inset-0 z-50 grid place-items-end bg-ink/50 p-4 sm:place-items-center" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={t("editRow", lang)} className="animate-fade flex max-h-[92dvh] w-full max-w-xl flex-col gap-4 overflow-y-auto rounded-tile bg-paper p-6 shadow-(--shadow-overlay)" onClick={(e) => e.stopPropagation()} data-testid="row-editor">
        <EditField label={t("medName", lang)} value={name} set={setName} inputRef={first} />
        <EditField label={t("medDose", lang)} value={dose} set={setDose} />
        <EditField label={t("medFreq", lang)} value={freq} set={setFreq} />
        <div className="grid gap-3 sm:grid-cols-2">
          <Button size="kiosk" variant="primary" icon={Check} loading={busy} disabled={!name.trim()} onClick={() => commit(false)} data-testid="ed-save">{t("save", lang)}</Button>
          <Button size="kiosk" icon={X} onClick={onClose} disabled={busy}>{t("back", lang)}</Button>
        </div>
        {cur && <Button size="kiosk" variant="ghost" icon={Trash2} disabled={busy} onClick={() => commit(true)}>{t("scanRemove", lang)}</Button>}
      </div>
    </div>
  );
}

function Banner({ text, action, testId }: { text: string; action?: ReactNode; testId?: string }) {
  return (
    <div role="alert" data-testid={testId} className="flex flex-wrap items-center gap-4 rounded-tile border-2 border-on-marigold/30 bg-marigold-tint px-5 py-4">
      <AlertTriangle size={30} aria-hidden className="shrink-0" />
      <p className="min-w-0 flex-1 text-k-body font-semibold">{text}</p>
      {action}
    </div>
  );
}
