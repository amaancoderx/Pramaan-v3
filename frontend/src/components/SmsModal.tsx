"use client";

import React, { useEffect, useRef, useState } from "react";
import { ImagePlus } from "lucide-react";
import { ApiError, matchSms, Verification } from "@/lib/api";
import { useLanguage } from "@/context/LanguageContext";
import { fileToBase64 } from "@/lib/format";
import { Alert, Button, Modal, Textarea } from "./ui";
import { cn } from "@/lib/utils";

function sampleSms(amount: string | null, utr: string | null) {
  const d = new Date();
  const date = [d.getDate(), d.getMonth() + 1, d.getFullYear() % 100].map((n) => String(n).padStart(2, "0")).join("-");
  const amt = amount && Number.isFinite(Number(amount)) ? Number(amount).toFixed(2) : "500.00";
  return `INR ${amt} credited to A/c XX4321 on ${date} by UPI Ref No ${utr || "429182736451"}. Avl Bal INR 18,240.50 - HDFC Bank`;
}

export function SmsModal({
  open,
  onClose,
  check,
  onDone,
}: {
  open: boolean;
  onClose: () => void;
  check: Verification;
  onDone: (v: Verification) => void;
}) {
  const { t } = useLanguage();
  const [tab, setTab] = useState<"text" | "image">("text");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setError(null);
      setFile(null);
    }
  }, [open]);

  const submit = async () => {
    setError(null);
    if ((tab === "text" && !text.trim()) || (tab === "image" && !file)) {
      setError(t.sms.empty);
      return;
    }
    setBusy(true);
    try {
      const payload = tab === "text" ? { sms_text: text.trim() } : { sms_image_base64: await fileToBase64(file as File) };
      const updated = await matchSms(check.id, payload);
      onDone(updated);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t.common.error);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t.sms.title}
      description={t.sms.body}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t.sms.cancel}
          </Button>
          <Button onClick={submit} loading={busy}>
            {t.sms.submit}
          </Button>
        </>
      }
    >
      <div className="mb-4 grid grid-cols-2 rounded-xl bg-paper p-1" role="tablist">
        {(["text", "image"] as const).map((k) => (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={tab === k}
            onClick={() => setTab(k)}
            className={cn("h-10 rounded-lg text-sm font-medium", tab === k ? "bg-surface text-ink shadow-card" : "text-muted")}
          >
            {k === "text" ? t.sms.pasteTab : t.sms.uploadTab}
          </button>
        ))}
      </div>

      {tab === "text" ? (
        <div className="space-y-3">
          <Textarea
            rows={5}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={t.sms.placeholder}
            className="font-mono text-[13px]"
            aria-label={t.sms.pasteTab}
          />
          <div className="flex flex-col gap-1 rounded-xl border border-line bg-paper p-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-muted">{t.sms.sampleNote}</p>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setText(sampleSms(check.extracted_data.amount.value, check.extracted_data.utr.value))}
              className="self-start sm:self-auto"
            >
              {t.sms.insertSample}
            </Button>
          </div>
        </div>
      ) : (
        <div>
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            className="flex w-full flex-col items-center gap-2 rounded-xl border-2 border-dashed border-line-strong px-4 py-8 text-sm text-muted hover:bg-paper"
          >
            <ImagePlus className="h-6 w-6" aria-hidden />
            <span className="font-medium text-ink">{file ? file.name : t.sms.chooseImage}</span>
          </button>
        </div>
      )}

      {error && (
        <Alert tone="danger" className="mt-4">
          {error}
        </Alert>
      )}
    </Modal>
  );
}
