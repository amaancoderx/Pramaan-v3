"use client";

import React, { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { FileQuestion, Landmark } from "lucide-react";
import { getPublicVerification, PublicVerification } from "@/lib/api";
import { useLanguage } from "@/context/LanguageContext";
import { Card, EmptyState, Skeleton } from "@/components/ui";
import { LogoMark } from "@/components/Logo";
import { appLabel, formatDateTime, formatINR, verdictStyle } from "@/lib/format";
import { cn } from "@/lib/utils";

export default function PublicCertificatePage() {
  const { t } = useLanguage();
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params.id);
  const [data, setData] = useState<PublicVerification | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    getPublicVerification(id)
      .then(setData)
      .catch(() => setMissing(true));
  }, [id]);

  if (missing) {
    return (
      <Card className="mx-auto max-w-md">
        <EmptyState
          icon={<FileQuestion className="h-5 w-5" />}
          title="Check not found"
          body="This report ID does not exist. Check the ID printed on the report."
        />
      </Card>
    );
  }

  if (!data) {
    return (
      <div className="mx-auto max-w-md space-y-3">
        <Skeleton className="h-32 rounded-2xl" />
        <Skeleton className="h-64 rounded-2xl" />
      </div>
    );
  }

  const s = verdictStyle(data.verdict);
  const gt =
    data.ground_truth_status === "SMS_MATCHED"
      ? t.result.smsMatched
      : data.ground_truth_status === "SMS_MISMATCH"
        ? t.result.smsMismatch
        : t.result.smsNone;

  const rows: [string, React.ReactNode][] = [
    ["Report ID", <span key="id" className="font-mono">{data.id}</span>],
    ["Shop", data.merchant_name],
    ["Amount", <span key="amt" className="tabular font-semibold">{formatINR(data.amount)}</span>],
    ["UTR", <span key="utr" className="font-mono">{data.utr_masked}</span>],
    ["App", appLabel(data.payment_app)],
    ["Checked at", formatDateTime(data.checked_at)],
    ["Risk score", <span key="score" className="tabular">{Math.round(data.risk_score)} / 100</span>],
  ];

  return (
    <div className="mx-auto max-w-md">
      <Card className="overflow-hidden">
        <div className={cn("px-6 py-6 text-white", s.solid)}>
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.08em] text-white/80">
            <LogoMark className="h-5 w-5" />
            Pramaan verification record
          </div>
          <p className="mt-3 text-3xl font-semibold tracking-tight">{t.verdict[data.verdict]}</p>
          <p className="mt-1 text-sm text-white/85">{t.verdictBasis[data.verdict]}</p>
        </div>
        <dl className="divide-y divide-line px-6">
          {rows.map(([k, v]) => (
            <div key={k} className="flex items-center justify-between gap-4 py-3 text-sm">
              <dt className="text-muted">{k}</dt>
              <dd className="text-right text-ink">{v}</dd>
            </div>
          ))}
        </dl>
        <div className="flex items-start gap-2 border-t border-line bg-paper px-6 py-4 text-sm">
          <Landmark className="mt-0.5 h-4 w-4 shrink-0 text-muted" aria-hidden />
          <span>{gt}</span>
        </div>
      </Card>
      <p className="mt-4 text-center text-xs text-muted">
        This page confirms a Pramaan check was run. It is not a bank statement.
      </p>
    </div>
  );
}
