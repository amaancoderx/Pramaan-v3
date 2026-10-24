"use client";

import { cn } from "@/lib/utils";
import { verdictStyle } from "@/lib/format";
import { useLanguage } from "@/context/LanguageContext";
import type { Severity, Verdict } from "@/lib/api";

export function VerdictChip({ verdict, className }: { verdict: Verdict | string; className?: string }) {
  const { t } = useLanguage();
  const s = verdictStyle(verdict);
  const label = t.verdict[verdict as Verdict] ?? verdict;
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium", s.soft, s.text, className)}>
      <span className={cn("h-1.5 w-1.5 rounded-full", s.solid)} aria-hidden />
      {label}
    </span>
  );
}

const SEVERITY_CLASS: Record<Severity, string> = {
  CRITICAL: "bg-fake-soft text-fake",
  HIGH: "bg-suspicious-soft text-suspicious",
  MEDIUM: "bg-suspicious-soft/70 text-suspicious",
  LOW: "bg-genuine-soft text-genuine",
  INFO: "bg-paper text-muted",
};

export function SeverityChip({ severity }: { severity: Severity }) {
  const { t } = useLanguage();
  return (
    <span className={cn("inline-flex rounded-md px-1.5 py-0.5 text-2xs font-semibold uppercase tracking-wide", SEVERITY_CLASS[severity] ?? SEVERITY_CLASS.INFO)}>
      {t.severity[severity] ?? severity}
    </span>
  );
}
