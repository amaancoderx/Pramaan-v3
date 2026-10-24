"use client";

import { AlertOctagon, AlertTriangle, CircleCheck, ShieldCheck } from "lucide-react";
import type { Verdict } from "@/lib/api";
import { useLanguage } from "@/context/LanguageContext";
import { verdictStyle } from "@/lib/format";
import { cn } from "@/lib/utils";

const ICONS = {
  CONFIRMED: ShieldCheck,
  "LIKELY GENUINE": CircleCheck,
  SUSPICIOUS: AlertTriangle,
  "LIKELY FAKE": AlertOctagon,
} as const;

export function VerdictCard({ verdict, score, reason }: { verdict: Verdict; score: number; reason: string }) {
  const { t, lang } = useLanguage();
  const s = verdictStyle(verdict);
  const Icon = ICONS[verdict] ?? AlertTriangle;

  return (
    <section className={cn("overflow-hidden rounded-2xl text-white", s.solid)} aria-live="polite">
      <div className="flex items-start gap-4 p-5 sm:p-7">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-white/15 sm:h-14 sm:w-14">
          <Icon className="h-7 w-7 sm:h-8 sm:w-8" aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium uppercase tracking-[0.08em] text-white/75">{t.verdictBasis[verdict]}</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight sm:text-4xl">{t.verdict[verdict]}</h1>
          <p className="mt-3 text-lg font-medium leading-snug sm:text-xl">{t.verdictInstruction[verdict]}</p>
          {lang === "en" && reason && <p className="mt-2 text-sm text-white/80">{reason}</p>}
        </div>
        <div className="hidden shrink-0 text-right sm:block">
          <p className="text-xs uppercase tracking-[0.08em] text-white/75">{t.result.riskScore}</p>
          <p className="tabular text-4xl font-semibold leading-none">
            {Math.round(score)}
            <span className="text-base font-normal text-white/70">/100</span>
          </p>
        </div>
      </div>
    </section>
  );
}
