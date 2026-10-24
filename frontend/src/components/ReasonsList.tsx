"use client";

import { useState } from "react";
import { AlertOctagon, AlertTriangle, ChevronDown, CircleCheck, Info, MapPin } from "lucide-react";
import type { PassedCheck, Reason, Severity } from "@/lib/api";
import { useLanguage } from "@/context/LanguageContext";
import { reasonTitle } from "@/lib/translations";
import { SeverityChip } from "./Chips";
import { cn } from "@/lib/utils";

const SEVERITY_ICON: Record<Severity, { icon: typeof Info; className: string }> = {
  CRITICAL: { icon: AlertOctagon, className: "text-fake" },
  HIGH: { icon: AlertTriangle, className: "text-suspicious" },
  MEDIUM: { icon: AlertTriangle, className: "text-suspicious" },
  LOW: { icon: Info, className: "text-genuine" },
  INFO: { icon: Info, className: "text-muted" },
};

function canShow(r: Reason) {
  return r.evidence_type === "heatmap" || r.evidence_type === "field" || !!r.region || !!r.field;
}

export function ReasonsList({
  reasons,
  passed,
  onShow,
  imageAvailable,
}: {
  reasons: Reason[];
  passed: PassedCheck[];
  onShow: (r: Reason) => void;
  imageAvailable: boolean;
}) {
  const { t, lang } = useLanguage();
  const [openPassed, setOpenPassed] = useState(false);

  return (
    <div>
      {reasons.length === 0 ? (
        <div className="flex items-start gap-3 rounded-xl border border-confirmed/20 bg-confirmed-soft p-4 text-sm text-ink">
          <CircleCheck className="mt-0.5 h-5 w-5 shrink-0 text-confirmed" aria-hidden />
          {t.result.noFindings}
        </div>
      ) : (
        <ol className="space-y-2">
          {reasons.map((r, i) => {
            const { icon: Icon, className } = SEVERITY_ICON[r.severity] ?? SEVERITY_ICON.INFO;
            const title = reasonTitle(r.code, r.title, lang);
            return (
              <li key={`${r.code}-${i}`} className="rounded-xl border border-line bg-surface p-4">
                <div className="flex items-start gap-3">
                  <Icon className={cn("mt-0.5 h-5 w-5 shrink-0", className)} aria-hidden />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <h3 className="text-sm font-semibold text-ink">{title}</h3>
                      <SeverityChip severity={r.severity} />
                    </div>
                    <p className="mt-1 text-sm leading-relaxed text-ink/80">{r.message}</p>
                    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                      <span>{t.result.layers[r.layer] ?? r.layer}</span>
                      {r.penalty > 0 && <span className="tabular">+{Math.round(r.penalty)} risk</span>}
                      {imageAvailable && canShow(r) && (
                        <button
                          type="button"
                          onClick={() => onShow(r)}
                          className="inline-flex min-h-[32px] items-center gap-1 font-medium text-accent-ink hover:underline"
                        >
                          <MapPin className="h-3.5 w-3.5" aria-hidden />
                          {t.result.showOnImage}
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      )}

      {passed.length > 0 && (
        <div className="mt-3 rounded-xl border border-line">
          <button
            type="button"
            onClick={() => setOpenPassed((v) => !v)}
            aria-expanded={openPassed}
            className="flex min-h-[48px] w-full items-center justify-between gap-2 px-4 text-sm font-medium text-ink"
          >
            <span className="flex items-center gap-2">
              <CircleCheck className="h-4 w-4 text-confirmed" aria-hidden />
              {passed.length} {t.result.passed}
            </span>
            <ChevronDown className={cn("h-4 w-4 text-muted transition-transform", openPassed && "rotate-180")} aria-hidden />
          </button>
          {openPassed && (
            <ul className="grid gap-x-4 gap-y-1.5 border-t border-line px-4 py-3 sm:grid-cols-2">
              {passed.map((p) => (
                <li key={p.code} className="flex items-start gap-2 text-sm text-ink/80">
                  <CircleCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-confirmed" aria-hidden />
                  <span>
                    {p.title}
                    <span className="ml-1 text-xs text-muted">· {t.result.layers[p.layer] ?? p.layer}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
