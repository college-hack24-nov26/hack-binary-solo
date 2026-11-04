import { Check } from "lucide-react";
import { t, type Lang } from "../../i18n/i18n";
import { cn } from "../../lib/cn";

/** "Step 1 of 3" with three labelled segments. Display only: the patient never jumps between steps from here. */
export function StepIndicator({ step, lang }: { step: 1 | 2 | 3; lang: Lang }) {
  const names = [t("step1", lang), t("step2", lang), t("step3", lang)];
  return (
    <nav aria-label={t("stepOf", lang, { n: step })} className="no-print border-b border-line bg-paper px-5 py-3 sm:px-8" data-testid="step-indicator" data-step={step}>
      <p className="text-k-body font-bold tabular" data-testid="step-text">
        {t("stepOf", lang, { n: step })}
      </p>
      <ol className="mt-2 grid grid-cols-3 gap-2">
        {names.map((name, i) => {
          const n = i + 1;
          const done = n < step;
          const here = n === step;
          return (
            <li key={name} aria-current={here ? "step" : undefined} className="min-w-0">
              <span className={cn("block h-2 rounded-full", done || here ? "bg-teal" : "bg-tint")} aria-hidden />
              <span className={cn("mt-1 flex items-center gap-1 text-base leading-snug", here ? "font-bold text-ink" : "text-muted")}>
                {done && <Check size={16} strokeWidth={3} aria-hidden className="shrink-0 text-teal" />}
                <span className="min-w-0">{name}</span>
              </span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
