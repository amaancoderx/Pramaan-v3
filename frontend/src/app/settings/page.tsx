"use client";

import React, { useEffect, useState } from "react";
import { Check, Copy, ExternalLink, KeyRound, RefreshCw } from "lucide-react";
import { ApiError, backendOrigin, getSettings, Merchant, rotateApiKey, Strictness, updateSettings } from "@/lib/api";
import { useLanguage } from "@/context/LanguageContext";
import { useAuth } from "@/context/AuthContext";
import { Alert, Button, Card, CardHeader, Input, Label, Modal, PageHeader, Skeleton } from "@/components/ui";
import { cn } from "@/lib/utils";

function CopyButton({ text, label, doneLabel }: { text: string; label: string; doneLabel: string }) {
  const [done, setDone] = useState(false);
  return (
    <Button
      variant="secondary"
      size="sm"
      icon={done ? <Check className="h-4 w-4 text-confirmed" /> : <Copy className="h-4 w-4" />}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setDone(true);
          window.setTimeout(() => setDone(false), 1800);
        } catch {
          // clipboard blocked
        }
      }}
    >
      {done ? doneLabel : label}
    </Button>
  );
}

export default function SettingsPage() {
  const { t } = useLanguage();
  const { setMerchant } = useAuth();
  const [m, setM] = useState<Merchant | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [upi, setUpi] = useState("");
  const [receiverName, setReceiverName] = useState("");
  const [windowMin, setWindowMin] = useState("60");
  const [strictness, setStrictness] = useState<Strictness>("standard");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [confirmRotate, setConfirmRotate] = useState(false);
  const [rotating, setRotating] = useState(false);
  const [origin, setOrigin] = useState("http://localhost:8000");

  const apply = (data: Merchant) => {
    setM(data);
    setName(data.name);
    setUpi(data.registered_upi_id);
    setReceiverName(data.registered_receiver_name || "");
    setWindowMin(String(data.allowed_window_minutes));
    setStrictness(data.strictness);
  };

  useEffect(() => {
    setOrigin(backendOrigin());
    getSettings()
      .then(apply)
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : t.settings.loadError));
  }, [t.settings.loadError]);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaved(false);
    const minutes = parseInt(windowMin, 10);
    if (!Number.isFinite(minutes) || minutes < 1) {
      setError(t.settings.windowHint);
      return;
    }
    setSaving(true);
    try {
      const updated = await updateSettings({
        name: name.trim(),
        registered_upi_id: upi.trim(),
        registered_receiver_name: receiverName.trim(),
        allowed_window_minutes: minutes,
        strictness,
      });
      apply(updated);
      setMerchant(updated);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t.common.error);
    } finally {
      setSaving(false);
    }
  };

  const rotate = async () => {
    setRotating(true);
    try {
      const updated = await rotateApiKey();
      apply(updated);
      setMerchant(updated);
      setConfirmRotate(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t.common.error);
      setConfirmRotate(false);
    } finally {
      setRotating(false);
    }
  };

  if (loadError) {
    return (
      <Alert tone="danger" title={t.settings.loadError}>
        {loadError}
      </Alert>
    );
  }

  if (!m) {
    return (
      <div className="grid gap-6 md:grid-cols-5">
        <Skeleton className="h-[480px] md:col-span-3" />
        <Skeleton className="h-[320px] md:col-span-2" />
      </div>
    );
  }

  const apiKey = m.api_key ?? "";
  const curl = `curl -X POST "${origin}/api/verify/analyze" \\\n  -H "X-API-Key: ${apiKey}" \\\n  -F "file=@screenshot.png"`;
  const levels: { key: Strictness; label: string; hint: string }[] = [
    { key: "lenient", label: t.settings.lenient, hint: t.settings.lenientHint },
    { key: "standard", label: t.settings.standard, hint: t.settings.standardHint },
    { key: "strict", label: t.settings.strict, hint: t.settings.strictHint },
  ];

  return (
    <div>
      <PageHeader title={t.settings.title} subtitle={t.settings.subtitle} />

      <div className="grid items-start gap-6 md:grid-cols-5">
        <Card className="md:col-span-3">
          <CardHeader title={t.settings.profile} hint={`${t.settings.account}: ${m.email}`} />
          <form onSubmit={save} className="space-y-5 p-5">
            <div>
              <Label htmlFor="name">{t.settings.name}</Label>
              <Input id="name" required value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="receiverName" hint={t.settings.receiverNameHint}>
                {t.settings.receiverName}
              </Label>
              <Input id="receiverName" required minLength={2} maxLength={100} value={receiverName}
                onChange={(e) => setReceiverName(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="upi" hint={t.settings.upiHint}>
                {t.settings.upi}
              </Label>
              <Input
                id="upi"
                required
                value={upi}
                onChange={(e) => setUpi(e.target.value)}
                className="font-mono"
                autoCapitalize="none"
                autoCorrect="off"
              />
            </div>
            <div>
              <Label htmlFor="window" hint={t.settings.windowHint}>
                {t.settings.window}
              </Label>
              <Input
                id="window"
                inputMode="numeric"
                value={windowMin}
                onChange={(e) => setWindowMin(e.target.value.replace(/\D/g, "").slice(0, 5))}
                className="tabular w-32"
              />
            </div>
            <fieldset>
              <legend className="mb-2 text-sm font-medium text-ink">{t.settings.strictness}</legend>
              <div className="grid gap-2 sm:grid-cols-3">
                {levels.map((l) => (
                  <label
                    key={l.key}
                    className={cn(
                      "flex cursor-pointer flex-col rounded-xl border p-3 transition-colors",
                      strictness === l.key ? "border-ink bg-paper" : "border-line hover:border-line-strong"
                    )}
                  >
                    <span className="flex items-center gap-2 text-sm font-medium text-ink">
                      <input
                        type="radio"
                        name="strictness"
                        value={l.key}
                        checked={strictness === l.key}
                        onChange={() => setStrictness(l.key)}
                        className="accent-[#0E1A2B]"
                      />
                      {l.label}
                    </span>
                    <span className="mt-1 text-xs text-muted">{l.hint}</span>
                  </label>
                ))}
              </div>
            </fieldset>

            {error && <Alert tone="danger">{error}</Alert>}

            <div className="flex items-center gap-3">
              <Button type="submit" loading={saving}>
                {saving ? t.settings.saving : t.settings.save}
              </Button>
              {saved && (
                <span className="flex items-center gap-1 text-sm text-confirmed" role="status">
                  <Check className="h-4 w-4" aria-hidden />
                  {t.settings.saved}
                </span>
              )}
            </div>
          </form>
        </Card>

        <Card className="md:col-span-2">
          <CardHeader title={t.settings.api} hint={t.settings.apiBody} />
          <div className="space-y-5 p-5">
            <div>
              <p className="mb-1.5 text-sm font-medium text-ink">{t.settings.apiKey}</p>
              <div className="flex items-center gap-2 rounded-xl border border-line bg-paper px-3 py-2.5">
                <KeyRound className="h-4 w-4 shrink-0 text-muted" aria-hidden />
                <code className="min-w-0 flex-1 truncate text-xs">{apiKey || "-"}</code>
              </div>
              <div className="mt-2 flex gap-2">
                <CopyButton text={apiKey} label={t.settings.copy} doneLabel={t.settings.copied} />
                <Button variant="ghost" size="sm" icon={<RefreshCw className="h-4 w-4" />} onClick={() => setConfirmRotate(true)}>
                  {t.settings.rotate}
                </Button>
              </div>
            </div>

            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <p className="text-sm font-medium text-ink">{t.settings.curl}</p>
                <CopyButton text={curl} label={t.settings.copy} doneLabel={t.settings.copied} />
              </div>
              <pre className="overflow-x-auto rounded-xl bg-ink p-3 text-[11px] leading-relaxed text-white/90">{curl}</pre>
            </div>

            <a
              href={`${origin}/docs`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-sm font-medium text-accent-ink hover:underline"
            >
              {t.settings.docs}
              <ExternalLink className="h-3.5 w-3.5" aria-hidden />
            </a>
          </div>
        </Card>
      </div>

      <Modal
        open={confirmRotate}
        onClose={() => setConfirmRotate(false)}
        title={t.settings.rotate}
        description={t.settings.rotateConfirm}
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmRotate(false)}>
              {t.settings.cancel}
            </Button>
            <Button variant="danger" onClick={rotate} loading={rotating}>
              {t.settings.rotateYes}
            </Button>
          </>
        }
      />
    </div>
  );
}
