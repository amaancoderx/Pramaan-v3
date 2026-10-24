"use client";

import { useLanguage } from "@/context/LanguageContext";
import { riskColor } from "@/lib/format";

export function RiskGauge({ score }: { score: number }) {
  const { t } = useLanguage();
  const value = Math.max(0, Math.min(100, score));
  const color = riskColor(value);
  const label = value >= 50 ? t.result.riskHigh : value >= 25 ? t.result.riskMedium : t.result.riskLow;

  // Semicircle from 180deg to 0deg.
  const r = 52;
  const len = Math.PI * r;
  const offset = len * (1 - value / 100);

  return (
    <div className="flex items-center gap-5">
      <svg viewBox="0 0 128 72" className="h-[72px] w-32 shrink-0" role="img" aria-label={`${t.result.riskScore}: ${Math.round(value)} / 100`}>
        <path d="M12 64 A52 52 0 0 1 116 64" fill="none" stroke="#E4E0D6" strokeWidth="10" strokeLinecap="round" />
        <path
          d="M12 64 A52 52 0 0 1 116 64"
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={len}
          strokeDashoffset={offset}
          style={{ transition: "stroke-dashoffset 600ms ease-out" }}
        />
        <text x="64" y="60" textAnchor="middle" className="tabular" fontSize="24" fontWeight="600" fill="#0E1A2B">
          {Math.round(value)}
        </text>
      </svg>
      <div>
        <p className="text-xs font-medium uppercase tracking-[0.08em] text-muted">{t.result.riskScore}</p>
        <p className="mt-1 text-base font-semibold" style={{ color }}>
          {label}
        </p>
        <p className="text-xs text-muted">0 = clean · 100 = high risk</p>
      </div>
    </div>
  );
}
