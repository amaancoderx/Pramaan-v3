"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Check, Copy, Download, QrCode, ScanLine } from "lucide-react";
import { ApiError, generateOrder, listOrders, Order } from "@/lib/api";
import { useLanguage } from "@/context/LanguageContext";
import { Alert, Button, Card, CardHeader, EmptyState, Input, Label, PageHeader, Skeleton } from "@/components/ui";
import { formatDateTime, formatINR } from "@/lib/format";
import { cn } from "@/lib/utils";

export default function QrPage() {
  const { t } = useLanguage();
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [order, setOrder] = useState<Order | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [orders, setOrders] = useState<Order[] | null>(null);

  const loadOrders = useCallback(() => {
    listOrders()
      .then((r) => setOrders(r.items))
      .catch(() => setOrders([]));
  }, []);

  useEffect(() => loadOrders(), [loadOrders]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const value = Number(amount);
    if (!Number.isFinite(value) || value <= 0) {
      setError(t.qr.invalidAmount);
      return;
    }
    setBusy(true);
    try {
      const created = await generateOrder(Math.round(value * 100) / 100, note.trim() || undefined);
      setOrder(created);
      setNote("");
      loadOrders();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t.common.error);
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    if (!order) return;
    try {
      await navigator.clipboard.writeText(order.upi_uri);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      // clipboard blocked; link is still visible for manual copy
    }
  };

  return (
    <div>
      <PageHeader title={t.qr.title} subtitle={t.qr.subtitle} />

      <div className="grid items-start gap-6 md:grid-cols-2">
        <Card className="p-5 sm:p-6">
          <form onSubmit={submit} className="space-y-4">
            <div>
              <Label htmlFor="amount">{t.qr.amount}</Label>
              <Input
                id="amount"
                inputMode="decimal"
                value={amount}
                onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ""))}
                placeholder="500"
                className="tabular h-12 text-lg font-semibold"
                required
              />
            </div>
            <div>
              <Label htmlFor="note" hint={t.qr.referenceHint}>
                {t.qr.reference}
              </Label>
              <Input
                id="note"
                value={note}
                onChange={(e) => setNote(e.target.value.toUpperCase().replace(/[^A-Z0-9-]/g, "").slice(0, 24))}
                placeholder="BILL-1042"
                className="font-mono"
              />
            </div>
            {error && <Alert tone="danger">{error}</Alert>}
            <Button type="submit" size="lg" className="w-full" loading={busy} icon={<QrCode className="h-5 w-5" />}>
              {busy ? t.qr.generating : t.qr.generate}
            </Button>
          </form>
        </Card>

        <Card className="p-5 sm:p-6">
          {order ? (
            <div className="flex flex-col items-center text-center animate-fade-up">
              <p className="text-xs font-medium uppercase tracking-[0.08em] text-muted">{t.qr.scanToPay}</p>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={order.qr_image_data_url} alt={`UPI QR ${order.order_ref}`} className="mt-3 h-56 w-56 rounded-xl border border-line" />
              <p className="tabular mt-4 text-3xl font-semibold tracking-tight">{formatINR(order.amount)}</p>
              <p className="mt-1 text-sm text-muted">
                {order.merchant_name} · <span className="font-mono">{order.merchant_upi_id}</span>
              </p>
              <p className="mt-3 rounded-lg bg-paper px-3 py-1.5 font-mono text-sm font-medium">{order.order_ref}</p>

              <div className="mt-5 grid w-full gap-2 sm:grid-cols-2">
                <Button variant="secondary" onClick={copy} icon={copied ? <Check className="h-4 w-4 text-confirmed" /> : <Copy className="h-4 w-4" />}>
                  {copied ? t.qr.copied : t.qr.copyLink}
                </Button>
                <a
                  href={order.qr_image_data_url}
                  download={`Pramaan_QR_${order.order_ref}.png`}
                  className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-line-strong bg-surface px-4 text-sm font-medium text-ink hover:bg-paper"
                >
                  <Download className="h-4 w-4" aria-hidden />
                  {t.qr.download}
                </a>
              </div>
              <Link
                href={`/?order=${encodeURIComponent(order.order_ref)}`}
                className="mt-2 inline-flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-ink px-4 text-sm font-medium text-white hover:bg-ink-2"
              >
                <ScanLine className="h-4 w-4" aria-hidden />
                {t.qr.verifyForOrder}
              </Link>
              <p className="mt-3 w-full break-all text-left font-mono text-2xs text-muted">{order.upi_uri}</p>
            </div>
          ) : (
            <EmptyState icon={<QrCode className="h-5 w-5" />} title={t.qr.emptyPreview} />
          )}
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader title={t.qr.recent} />
        {orders === null ? (
          <div className="space-y-2 p-4">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-12" />
            ))}
          </div>
        ) : orders.length === 0 ? (
          <p className="px-5 py-6 text-sm text-muted">{t.qr.noOrders}</p>
        ) : (
          <ul className="divide-y divide-line">
            {orders.map((o) => (
              <li key={o.order_ref} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3">
                <div className="min-w-0">
                  <p className="font-mono text-sm font-medium">{o.order_ref}</p>
                  <p className="text-xs text-muted">{formatDateTime(o.created_at)}</p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="tabular text-sm font-semibold">{formatINR(o.amount)}</span>
                  <span
                    className={cn(
                      "rounded-full px-2.5 py-0.5 text-xs font-medium",
                      o.status === "paid" ? "bg-confirmed-soft text-confirmed" : "bg-paper text-muted"
                    )}
                  >
                    {o.status === "paid" ? t.qr.paid : t.qr.open}
                  </span>
                  {o.status === "paid" && o.verification_id ? (
                    <Link href={`/checks/${encodeURIComponent(o.verification_id)}`} className="text-sm font-medium text-accent-ink hover:underline">
                      {o.verification_id}
                    </Link>
                  ) : (
                    <Link href={`/?order=${encodeURIComponent(o.order_ref)}`} className="text-sm font-medium text-accent-ink hover:underline">
                      {t.nav.verify}
                    </Link>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
