"use client";

import type { Field, FieldKey, Verification } from "@/lib/api";
import { useLanguage } from "@/context/LanguageContext";
import { appLabel, formatINR } from "@/lib/format";
import { cn } from "@/lib/utils";

const ORDER: FieldKey[] = ["amount", "utr", "receiver_upi_id", "receiver", "timestamp", "status"];

function display(key: FieldKey, f: Field) {
  if (!f.value) return null;
  if (key === "amount") {
    const n = Number(f.value);
    return Number.isFinite(n) ? formatINR(n) : f.value;
  }
  return f.value;
}

export function FieldsPanel({ check, onFocus }: { check: Verification; onFocus: (field: FieldKey) => void }) {
  const { t } = useLanguage();
  const data = check.extracted_data;

  return (
    <>
      {data.document_type === "history_list" && (
        <div className="mb-3 rounded-xl border border-amber-300 bg-amber-50 px-3 py-3 text-sm text-amber-950">
          <strong className="block">Transaction history screen detected</strong>
          This image contains multiple payment rows. Open the individual transaction details for reliable receiver,
          date/time and UPI reference extraction. A history-list screenshot is not treated as proof of editing.
        </div>
      )}
      <dl className="divide-y divide-line">
      {ORDER.map((key) => {
        const f = data[key];
        const value = display(key, f);
        const conf = Math.round((f.confidence || 0) * 100);
        const mono = key === "utr" || key === "receiver_upi_id";
        return (
          <div key={key} className="flex items-start justify-between gap-4 py-3 first:pt-0">
            <div className="min-w-0 flex-1">
              <dt className="text-xs text-muted">{t.fields[key]}</dt>
              <dd className="mt-0.5 min-w-0">
                {value ? (
                  <button
                    type="button"
                    onClick={() => onFocus(key)}
                    disabled={!f.bbox || !check.image_available}
                    className={cn(
                      "block max-w-full truncate text-left text-sm font-medium text-ink enabled:hover:underline disabled:cursor-default",
                      mono && "font-mono",
                      key === "amount" && "tabular text-lg font-semibold",
                      !f.is_valid && "text-fake"
                    )}
                    title={f.value ?? undefined}
                  >
                    {value}
                  </button>
                ) : (
                  <span className="text-sm text-muted">{t.result.notFound}</span>
                )}
                {value && !f.corrected && (
                  <div className="mt-1.5 flex items-center gap-2">
                    <div className="h-1 w-20 overflow-hidden rounded-full bg-line">
                      <div
                        className={cn("h-full", conf >= 80 ? "bg-confirmed" : conf >= 50 ? "bg-suspicious" : "bg-fake")}
                        style={{ width: `${conf}%` }}
                      />
                    </div>
                    <span className="tabular text-2xs text-muted">
                      {conf}% {t.result.confidence}
                    </span>
                  </div>
                )}
              </dd>
            </div>
            <div className="flex shrink-0 items-center gap-2 pt-4">
              {f.corrected && (
                <span className="rounded-md bg-genuine-soft px-1.5 py-0.5 text-2xs font-semibold uppercase tracking-wide text-genuine">
                  {t.result.corrected}
                </span>
              )}
              {!f.is_valid && value && <span className="h-2 w-2 rounded-full bg-fake" aria-label="Flagged" />}
            </div>
          </div>
        );
      })}
      <div className="flex items-center justify-between py-3 last:pb-0">
        <span className="text-xs text-muted">{t.result.app}</span>
        <span className="text-sm font-medium text-ink">{appLabel(data.payment_app)}</span>
      </div>
      </dl>
    </>
  );
}
