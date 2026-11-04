import { Delete } from "lucide-react";
import { tapFeedback } from "../../components/Tile";
import { t, type Lang } from "../../i18n/i18n";

/** On-screen digits (never the OS keyboard): 1-9, a spare slot, 0 and delete. 72 px keys. */
export function NumberPad({ onDigit, onDelete, lang, disabled }: { onDigit: (d: string) => void; onDelete: () => void; lang: Lang; disabled?: boolean }) {
  const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "del"];
  return (
    <div className="mx-auto grid w-full max-w-md grid-cols-3 gap-3" data-testid="number-pad">
      {keys.map((k, i) =>
        k === "" ? (
          <span key={i} aria-hidden />
        ) : (
          <button
            key={k}
            type="button"
            disabled={disabled}
            data-testid={`key-${k}`}
            aria-label={k === "del" ? t("deleteDigit", lang) : k}
            onClick={() => {
              tapFeedback();
              if (k === "del") onDelete();
              else onDigit(k);
            }}
            className="flex min-h-[4.5rem] items-center justify-center rounded-tile border-2 border-b-[5px] border-line-strong bg-surface text-[2rem] font-bold tabular transition-transform duration-(--dur-feedback) active:translate-y-[3px] active:border-b-2 disabled:opacity-50"
          >
            {k === "del" ? <Delete size={32} aria-hidden /> : k}
          </button>
        ),
      )}
    </div>
  );
}
