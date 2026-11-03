import { Check } from "lucide-react";
import type { TokenSlip as Slip } from "../api/client";
import { t, type Lang } from "../i18n/i18n";
import { cn } from "../lib/cn";

/**
 * The parchi: perforated edge, large queue number, token, doctor and room, then the floor-line stripe with
 * "Follow the green line to Room 12". Only queue number, token, doctor and room. No name, no answers, no red flags.
 */
export function TokenSlip({ slip, lang, stamped }: { slip: Slip; lang: Lang; stamped?: boolean }) {
  const d = slip.doctor;
  const line = d?.lineColor;
  const lineName = d?.lineName?.[lang] ?? d?.lineName?.en;
  const date = new Date(`${slip.queueDate}T00:00:00`);
  const dateText = date.toLocaleDateString(`${lang}-IN-u-nu-latn`, { day: "numeric", month: "short", year: "numeric" });
  const where =
    slip.guidance === "follow_line" && slip.room && lineName
      ? t("followLine", lang, { line: lineName, room: slip.room })
      : slip.room
        ? t("goToRoom", lang, { room: slip.room })
        : t("reception", lang);
  return (
    <div className="print-area parchi relative mx-auto w-full max-w-md bg-surface px-7 pb-7 pt-8 shadow-[0_1px_0_var(--line),0_0_0_1px_var(--line)]" data-testid="token-slip">
      <div className="flex items-baseline justify-between border-b-2 border-dashed border-line pb-3">
        <p className="text-k-body font-bold text-teal">{t("tokenTitle", lang)}</p>
        <p className="text-k-body text-muted tabular">{dateText}</p>
      </div>

      <div className="relative py-5 text-center">
        <p className="text-k-body text-muted">{t("queueLabel", lang)}</p>
        <p className="text-k-queue font-bold tabular" data-testid="queue-number">
          {slip.queueNumber}
        </p>
        <p className="mt-1 text-k-lead font-semibold tabular tracking-normal">{slip.token}</p>
        {stamped && (
          <span className="absolute bottom-14 right-0" data-testid="stamp">
            <span className="animate-stamp inline-flex items-center gap-1 rounded-full border-[3px] border-green bg-surface/80 px-3 py-1 text-k-body font-bold text-green">
              <Check size={22} strokeWidth={3} aria-hidden />
              {t("stamp", lang)}
            </span>
          </span>
        )}
      </div>

      <div className="border-t-2 border-dashed border-line pt-4">
        <p className="text-k-body text-muted">{t("doctorLabel", lang)}</p>
        <p className="text-k-lead font-semibold">{d ? d.name : t("anyDoctorSlip", lang)}</p>
        {d && <p className="text-k-body text-muted">{d.specialty[lang] ?? d.specialty.en}</p>}
        {slip.room && (
          <p className="mt-2 text-k-lead font-bold tabular">
            {t("room", lang, { room: slip.room })}
            {slip.floor && <span className="font-normal text-muted"> · {slip.floor[lang] ?? slip.floor.en}</span>}
          </p>
        )}
      </div>

      {line ? (
        <div className="mt-4">
          <div
            className={cn("h-5 rounded-sm", line.toUpperCase() === "#F2B33D" && "border-2 border-ink")}
            style={{ backgroundColor: line }}
            data-testid="floor-line"
            aria-hidden
          />
          <p className="mt-2 text-k-lead font-bold">{where}</p>
        </div>
      ) : (
        <p className="mt-4 text-k-lead font-bold">{where}</p>
      )}

      <p className="mt-4 text-k-body text-muted tabular">
        {slip.patientsAhead > 0 ? (
          <>
            {t("waitEstimate", lang, { min: slip.estimatedWaitMinutes })} · {t("ahead", lang, { n: slip.patientsAhead })}
          </>
        ) : (
          t("next", lang)
        )}
      </p>
    </div>
  );
}
