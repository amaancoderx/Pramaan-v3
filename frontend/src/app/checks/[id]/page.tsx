"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  CheckCheck,
  Copy,
  Download,
  Landmark,
  MessageSquareText,
  Pencil,
  ReceiptText,
  RotateCcw,
} from "lucide-react";
import {
  ApiError,
  downloadReport,
  FieldKey,
  getVerification,
  Reason,
  setHandled,
  Verification,
} from "@/lib/api";
import { useLanguage } from "@/context/LanguageContext";
import { Alert, Button, Card, CardHeader, Skeleton } from "@/components/ui";
import { VerdictCard } from "@/components/VerdictCard";
import { RiskGauge } from "@/components/RiskGauge";
import { ImageViewer, ViewerFocus, ViewMode } from "@/components/ImageViewer";
import { FieldsPanel } from "@/components/FieldsPanel";
import { ReasonsList } from "@/components/ReasonsList";
import { FieldEditorModal } from "@/components/FieldEditorModal";
import { SmsModal } from "@/components/SmsModal";
import { formatDateTime, formatINR } from "@/lib/format";
import { cn } from "@/lib/utils";

function LoadingView() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-40 w-full rounded-2xl" />
      <div className="grid gap-6 lg:grid-cols-12">
        <Skeleton className="h-[480px] lg:col-span-5" />
        <div className="space-y-4 lg:col-span-7">
          <Skeleton className="h-28" />
          <Skeleton className="h-64" />
        </div>
      </div>
    </div>
  );
}

function ReusedBanner({ check }: { check: Verification }) {
  const { t } = useLanguage();
  const first = check.reused_first_seen;
  if (!check.is_reused || !first) return null;
  return (
    <Alert tone="danger" title={t.result.reusedTitle} icon={<Copy className="h-5 w-5 text-fake" />}>
      <p>
        {t.result.reusedBody} {formatDateTime(first.seen_at)}
        {first.same_merchant ? "." : ` ${t.result.reusedOther}`}
      </p>
      {first.same_merchant && first.id !== check.id && (
        <Link href={`/checks/${encodeURIComponent(first.id)}`} className="mt-2 inline-block font-medium text-fake underline">
          {t.result.openFirst} ({first.id})
        </Link>
      )}
    </Alert>
  );
}

function GroundTruthPanel({ check, onConfirm }: { check: Verification; onConfirm: () => void }) {
  const { t } = useLanguage();
  const gt = check.ground_truth;
  const tone = gt.status === "SMS_MATCHED" ? "success" : gt.status === "SMS_MISMATCH" ? "danger" : "neutral";
  const title =
    gt.status === "SMS_MATCHED" ? t.result.smsMatched : gt.status === "SMS_MISMATCH" ? t.result.smsMismatch : t.result.smsNone;

  return (
    <Card>
      <CardHeader title={t.result.smsTitle} />
      <div className="space-y-3 p-5">
        <Alert tone={tone} icon={<Landmark className="h-5 w-5" />} title={title}>
          {gt.message && <p>{gt.message}</p>}
        </Alert>
        {gt.status !== "NONE" && (
          <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-xs text-muted">{t.result.smsAmount}</dt>
              <dd className={cn("tabular font-medium", gt.amount_matched === false && "text-fake")}>{formatINR(gt.sms_amount)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted">{t.result.smsUtr}</dt>
              <dd className={cn("font-mono font-medium", gt.utr_matched === false && "text-fake")}>{gt.sms_utr ?? "-"}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted">{t.result.smsBank}</dt>
              <dd className="font-medium">
                {gt.bank ?? "-"}
                {gt.account_masked ? ` · ${gt.account_masked}` : ""}
              </dd>
            </div>
          </dl>
        )}
        {check.verdict !== "CONFIRMED" && (
          <Button className="w-full sm:w-auto" icon={<MessageSquareText className="h-4 w-4" />} onClick={onConfirm}>
            {t.result.confirmSms}
          </Button>
        )}
      </div>
    </Card>
  );
}

function OrderPanel({ check }: { check: Verification }) {
  const { t } = useLanguage();
  const o = check.order;
  if (!o) return null;
  const message =
    o.matched_by === "reference" ? t.result.orderMatchedRef : o.matched_by === "amount" ? t.result.orderMatchedAmount : t.result.orderNotMatched;
  return (
    <Alert
      tone={o.matched_by === "reference" ? "success" : o.matched_by === "amount" ? "warning" : "danger"}
      icon={<ReceiptText className="h-5 w-5" />}
      title={`${t.result.orderTitle}: ${o.order_ref} · ${formatINR(o.amount)}`}
    >
      {message}
    </Alert>
  );
}

export default function CheckPage() {
  const { t } = useLanguage();
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params.id);

  const [check, setCheck] = useState<Verification | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<ViewMode>("original");
  const [focus, setFocus] = useState<ViewerFocus | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [smsOpen, setSmsOpen] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [handledBusy, setHandledBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const viewerRef = useRef<HTMLDivElement>(null);

  const load = useCallback(() => {
    setError(null);
    getVerification(id)
      .then(setCheck)
      .catch((err) => setError(err instanceof ApiError ? err.message : t.result.loadError));
  }, [id, t.result.loadError]);

  useEffect(() => {
    load();
  }, [load]);

  const scrollToViewer = () => viewerRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });

  const showReason = (r: Reason) => {
    setMode(r.evidence_type === "heatmap" ? "heatmap" : "original");
    setFocus({ field: r.field, region: r.region });
    scrollToViewer();
  };

  const focusField = (field: FieldKey) => {
    setMode("original");
    setFocus({ field });
    scrollToViewer();
  };

  const onDownload = async () => {
    if (!check) return;
    setActionError(null);
    setDownloading(true);
    try {
      await downloadReport(check.id);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : t.common.error);
    } finally {
      setDownloading(false);
    }
  };

  const toggleHandled = async () => {
    if (!check) return;
    setActionError(null);
    setHandledBusy(true);
    try {
      setCheck(await setHandled(check.id, !check.handled));
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : t.common.error);
    } finally {
      setHandledBusy(false);
    }
  };

  if (error) {
    return (
      <div className="mx-auto max-w-lg space-y-4">
        <Alert tone="danger" title={t.result.loadError}>
          {error}
        </Alert>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={load}>
            {t.common.retry}
          </Button>
          <Button variant="ghost" onClick={() => router.push("/")}>
            {t.result.verifyAnother}
          </Button>
        </div>
      </div>
    );
  }

  if (!check) return <LoadingView />;

  return (
    <div className="space-y-6 animate-fade-up">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => (window.history.length > 1 ? router.back() : router.push("/dashboard"))}
          className="inline-flex h-10 items-center gap-1.5 rounded-lg pr-2 text-sm font-medium text-muted hover:text-ink"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          {t.result.back}
        </button>
        <p className="text-xs text-muted">
          {t.result.checkId} <span className="font-mono text-ink">{check.id}</span> · {formatDateTime(check.created_at)}
          {check.processing_time_seconds > 0 && (
            <>
              {" "}
              · {t.result.processedIn} <span className="tabular">{check.processing_time_seconds.toFixed(1)}s</span>
            </>
          )}
        </p>
      </div>

      {check.check_mode === "authenticity" && (
        <p className="w-fit rounded-full border border-line bg-surface px-3 py-1 text-xs font-medium text-muted">
          {t.verify.modeAuthenticity} · {t.verify.modeAuthenticityHint}
        </p>
      )}

      <VerdictCard verdict={check.verdict} score={check.risk_score} reason={check.final_verdict_reason} />
      <p className="-mt-3 text-xs text-muted">{t.result.riskScoreHint}</p>

      {check.handled && (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-line bg-surface px-4 py-3 text-sm">
          <span className="flex items-center gap-2 font-medium text-ink">
            <CheckCheck className="h-4 w-4 text-confirmed" aria-hidden />
            {t.result.handled}
            {check.handled_at && <span className="font-normal text-muted">· {formatDateTime(check.handled_at)}</span>}
          </span>
        </div>
      )}

      <ReusedBanner check={check} />
      <OrderPanel check={check} />
      {actionError && <Alert tone="danger">{actionError}</Alert>}

      <div className="grid items-start gap-6 lg:grid-cols-12">
        <div className="space-y-4 lg:sticky lg:top-24 lg:col-span-5">
          <ImageViewer ref={viewerRef} check={check} mode={mode} onModeChange={setMode} focus={focus} />
          <div className="grid grid-cols-2 gap-2">
            <Button variant="secondary" icon={<Download className="h-4 w-4" />} onClick={onDownload} loading={downloading}>
              {downloading ? t.result.downloading : t.result.downloadReport}
            </Button>
            <Button variant="secondary" icon={<RotateCcw className="h-4 w-4" />} onClick={() => router.push("/")}>
              {t.result.verifyAnother}
            </Button>
          </div>
        </div>

        <div className="space-y-6 lg:col-span-7">
          <Card className="p-5">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <RiskGauge score={check.risk_score} />
              <div className="flex flex-col gap-2 sm:items-end">
                {check.verdict !== "CONFIRMED" && (
                  <Button icon={<MessageSquareText className="h-4 w-4" />} onClick={() => setSmsOpen(true)}>
                    {t.result.confirmSms}
                  </Button>
                )}
                <Button
                  variant={check.handled ? "ghost" : "secondary"}
                  icon={<CheckCheck className="h-4 w-4" />}
                  onClick={toggleHandled}
                  loading={handledBusy}
                >
                  {check.handled ? t.result.undoHandled : t.result.markHandled}
                </Button>
              </div>
            </div>
          </Card>

          <Card>
            <CardHeader
              title={t.result.details}
              hint={t.result.detailsHint}
              action={
                <Button variant="ghost" size="sm" icon={<Pencil className="h-4 w-4" />} onClick={() => setEditOpen(true)}>
                  {t.result.edit}
                </Button>
              }
            />
            <div className="p-5">
              <FieldsPanel check={check} onFocus={focusField} />
            </div>
          </Card>

          <section aria-labelledby="findings">
            <h2 id="findings" className="mb-3 text-sm font-semibold text-ink">
              {t.result.findings}
            </h2>
            <ReasonsList
              reasons={check.reasons}
              passed={check.passed_checks}
              onShow={showReason}
              imageAvailable={check.image_available}
            />
          </section>

          <GroundTruthPanel check={check} onConfirm={() => setSmsOpen(true)} />
        </div>
      </div>

      <FieldEditorModal open={editOpen} onClose={() => setEditOpen(false)} check={check} onSaved={setCheck} />
      <SmsModal open={smsOpen} onClose={() => setSmsOpen(false)} check={check} onDone={setCheck} />
    </div>
  );
}
