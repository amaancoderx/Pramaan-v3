"use client";

import React, { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, Camera, Check, FileImage, ImageOff, Landmark, ListChecks, ScanSearch, Upload, WifiOff, X } from "lucide-react";
import { analyzeScreenshot, ApiError, CheckMode, DemoSample, fetchDemoSample, listDemoSamples, listOrders, Order } from "@/lib/api";
import { useLanguage } from "@/context/LanguageContext";
import { Alert, Button, Card, Label, Select, Skeleton, Spinner } from "@/components/ui";
import { formatINR } from "@/lib/format";
import { cn } from "@/lib/utils";

const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPTED = ["image/png", "image/jpeg", "image/jpg", "image/webp"];

type UploadError = { kind: "quality" | "size" | "type" | "offline" | "other"; message: string };

function toUploadError(err: unknown, t: ReturnType<typeof useLanguage>["t"]): UploadError {
  if (err instanceof ApiError) {
    if (err.code === "IMAGE_QUALITY_LOW") return { kind: "quality", message: err.message };
    if (err.code === "FILE_TOO_LARGE" || err.status === 413) return { kind: "size", message: t.verify.errTooLarge };
    if (err.code === "NOT_AN_IMAGE" || err.status === 415) return { kind: "type", message: t.verify.errNotImage };
    if (err.code === "OFFLINE") return { kind: "offline", message: t.verify.errOffline };
    return { kind: "other", message: err.message };
  }
  return { kind: "other", message: t.common.error };
}

function Progress({ elapsed }: { elapsed: number }) {
  const { t } = useLanguage();
  const steps = [t.verify.step1, t.verify.step2, t.verify.step3];
  const active = elapsed < 1.2 ? 0 : elapsed < 2.6 ? 1 : 2;
  return (
    <Card className="mx-auto max-w-lg p-6 sm:p-8" aria-live="polite">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-ink">{t.verify.analyzing}</h2>
        <span className="tabular text-sm text-muted">
          {elapsed.toFixed(1)}
          {t.verify.elapsed}
        </span>
      </div>
      <ol className="mt-6 space-y-4">
        {steps.map((label, i) => {
          const done = i < active;
          const current = i === active;
          return (
            <li key={label} className="flex items-center gap-3 text-sm">
              <span
                className={cn(
                  "flex h-7 w-7 shrink-0 items-center justify-center rounded-full border",
                  done && "border-confirmed bg-confirmed text-white",
                  current && "border-accent text-accent",
                  !done && !current && "border-line text-muted"
                )}
              >
                {done ? <Check className="h-4 w-4" aria-hidden /> : current ? <Spinner className="h-4 w-4 text-accent" /> : i + 1}
              </span>
              <span className={cn(current ? "font-medium text-ink" : done ? "text-ink" : "text-muted")}>{label}</span>
            </li>
          );
        })}
      </ol>
      <div className="mt-6 h-1 overflow-hidden rounded-full bg-line">
        <div className="h-full bg-accent transition-all duration-500" style={{ width: `${Math.min(95, (elapsed / 6) * 100)}%` }} />
      </div>
    </Card>
  );
}

function ErrorPanel({ error, onReset }: { error: UploadError; onReset: () => void }) {
  const { t } = useLanguage();
  if (error.kind === "quality") {
    return (
      <Alert tone="warning" title={t.verify.errQualityTitle} icon={<ImageOff className="h-5 w-5 text-suspicious" />}>
        <p>{error.message}</p>
        <ul className="mt-2 list-disc space-y-1 pl-5">
          {t.verify.errQualityTips.map((tip) => (
            <li key={tip}>{tip}</li>
          ))}
        </ul>
        <Button variant="secondary" size="sm" className="mt-3" onClick={onReset}>
          {t.verify.tryAgain}
        </Button>
      </Alert>
    );
  }
  return (
    <Alert
      tone="danger"
      title={t.verify.errTitle}
      icon={error.kind === "offline" ? <WifiOff className="h-5 w-5 text-fake" /> : <AlertTriangle className="h-5 w-5 text-fake" />}
    >
      <p>{error.message}</p>
    </Alert>
  );
}

function VerifyPage() {
  const { t } = useLanguage();
  const router = useRouter();
  const params = useSearchParams();

  const [orders, setOrders] = useState<Order[]>([]);
  const [orderRef, setOrderRef] = useState<string>(params.get("order") ?? "");
  const [mode, setMode] = useState<CheckMode>("merchant");
  useEffect(() => {
    try {
      if (window.localStorage.getItem("pramaan_mode") === "authenticity") setMode("authenticity");
    } catch {
      // storage unavailable; keep the default
    }
  }, []);
  const chooseMode = (m: CheckMode) => {
    setMode(m);
    try {
      window.localStorage.setItem("pramaan_mode", m);
    } catch {
      // storage unavailable; the choice lasts for this visit
    }
  };
  const [samples, setSamples] = useState<DemoSample[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<UploadError | null>(null);
  const [dragging, setDragging] = useState(false);

  const fileRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const cameraStreamRef = useRef<MediaStream | null>(null);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);

  useEffect(() => {
    listOrders("open")
      .then((r) => setOrders(r.items))
      .catch(() => setOrders([]));
    listDemoSamples()
      .then((r) => setSamples(r.items))
      .catch(() => setSamples([]));
  }, []);

  useEffect(() => {
    if (!busy) return;
    const start = performance.now();
    const id = window.setInterval(() => setElapsed((performance.now() - start) / 1000), 100);
    return () => window.clearInterval(id);
  }, [busy]);

  useEffect(() => {
    if (!cameraOpen) return;
    let cancelled = false;
    setCameraError(null);
    const startCamera = async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("Live camera is unavailable in this browser. Choose an image file instead.");
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false,
      });
      if (cancelled) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      cameraStreamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => undefined);
      }
    };
    startCamera().catch((err: unknown) => {
      if (!cancelled) setCameraError(err instanceof Error ? err.message : "Could not open the camera. Check browser permissions.");
    });
    return () => {
      cancelled = true;
      cameraStreamRef.current?.getTracks().forEach((track) => track.stop());
      cameraStreamRef.current = null;
    };
  }, [cameraOpen]);

  const run = useCallback(
    async (file: File) => {
      setError(null);
      if (!navigator.onLine) {
        setError({ kind: "offline", message: t.verify.errOffline });
        return;
      }
      if (file.size > MAX_BYTES) {
        setError({ kind: "size", message: t.verify.errTooLarge });
        return;
      }
      if (file.type && !ACCEPTED.includes(file.type.toLowerCase())) {
        setError({ kind: "type", message: t.verify.errNotImage });
        return;
      }
      setElapsed(0);
      setBusy(true);
      try {
        const result = await analyzeScreenshot(file, orderRef || null, mode);
        router.push(`/checks/${encodeURIComponent(result.id)}`);
      } catch (err) {
        setError(toUploadError(err, t));
        setBusy(false);
      }
    },
    [orderRef, mode, router, t]
  );

  const runSample = async (key: string) => {
    setError(null);
    setElapsed(0);
    setBusy(true);
    try {
      const file = await fetchDemoSample(key);
      const result = await analyzeScreenshot(file, orderRef || null, mode);
      router.push(`/checks/${encodeURIComponent(result.id)}`);
    } catch (err) {
      setError(toUploadError(err, t));
      setBusy(false);
    }
  };

  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (f) run(f);
  };

  const captureFromCamera = () => {
    const video = videoRef.current;
    if (!video || !video.videoWidth || !video.videoHeight) {
      setCameraError("Camera is still starting. Wait a moment and try again.");
      return;
    }
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext("2d");
    if (!context) {
      setCameraError("Could not capture the camera frame. Please choose an image instead.");
      return;
    }
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => {
      if (!blob) {
        setCameraError("Could not capture the camera frame. Please try again.");
        return;
      }
      const file = new File([blob], `pramaan-camera-${Date.now()}.jpg`, { type: "image/jpeg" });
      cameraStreamRef.current?.getTracks().forEach((track) => track.stop());
      cameraStreamRef.current = null;
      setCameraOpen(false);
      run(file);
    }, "image/jpeg", 0.94);
  };

  if (busy) return <Progress elapsed={elapsed} />;

  const selectedOrder = orders.find((o) => o.order_ref === orderRef);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">{t.verify.title}</h1>
        <p className="mt-2 text-sm text-muted sm:text-base">{t.verify.subtitle}</p>
      </div>

      <div role="radiogroup" aria-label={t.verify.modeTitle} className="grid gap-3 sm:grid-cols-2">
        {(
          [
            ["merchant", t.verify.modeMerchant, t.verify.modeMerchantHint],
            ["authenticity", t.verify.modeAuthenticity, t.verify.modeAuthenticityHint],
          ] as const
        ).map(([value, label, hint]) => (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={mode === value}
            onClick={() => chooseMode(value)}
            className={cn(
              "rounded-xl border bg-surface px-4 py-3 text-left transition-colors",
              mode === value ? "border-ink ring-1 ring-ink" : "border-line hover:border-line-strong"
            )}
          >
            <span className="block text-sm font-semibold text-ink">{label}</span>
            <span className="mt-0.5 block text-xs text-muted">{hint}</span>
          </button>
        ))}
      </div>

      <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={onPick} />
      <input ref={cameraRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={onPick} />

      {cameraOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-3 sm:p-6" role="dialog" aria-modal="true" aria-labelledby="camera-title">
          <div className="w-full max-w-3xl overflow-hidden rounded-2xl border border-line bg-surface shadow-2xl">
            <div className="flex items-center justify-between gap-4 border-b border-line px-4 py-3 sm:px-6">
              <div>
                <h2 id="camera-title" className="text-lg font-semibold text-ink">{t.verify.cameraTitle}</h2>
                <p className="text-sm text-muted">{t.verify.cameraHint}</p>
              </div>
              <button type="button" aria-label={t.common.close} onClick={() => setCameraOpen(false)} className="rounded-lg p-2 text-muted hover:bg-paper hover:text-ink">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="bg-black">
              <video ref={videoRef} autoPlay playsInline muted className="max-h-[65vh] w-full object-contain" />
            </div>
            <div className="space-y-3 p-4 sm:p-6">
              {cameraError && <Alert tone="warning" title={t.verify.cameraProblem}>{cameraError}</Alert>}
              <p className="text-xs text-muted">{t.verify.cameraSafety}</p>
              <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                <Button variant="secondary" onClick={() => { setCameraOpen(false); cameraRef.current?.click(); }}>
                  {t.verify.useDeviceCamera}
                </Button>
                <Button onClick={captureFromCamera} icon={<Camera className="h-4 w-4" />}>
                  {t.verify.captureVerify}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const f = e.dataTransfer.files?.[0];
          if (f) run(f);
        }}
        className={cn(
          "rounded-2xl border-2 border-dashed bg-surface px-6 py-10 text-center transition-colors sm:py-14",
          dragging ? "border-accent bg-accent-soft/40" : "border-line-strong"
        )}
      >
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-paper text-ink">
          <Upload className="h-6 w-6" aria-hidden />
        </div>
        <p className="mt-4 text-base font-semibold text-ink">{t.verify.dropTitle}</p>
        <p className="mt-1 text-sm text-muted">{t.verify.dropHint}</p>
        <div className="mx-auto mt-6 flex max-w-sm flex-col gap-3 sm:flex-row sm:justify-center">
          <Button size="lg" icon={<Camera className="h-5 w-5" />} onClick={() => { setCameraError(null); setCameraOpen(true); }} className="sm:flex-1">
            {t.verify.takePhoto}
          </Button>
          <Button
            size="lg"
            variant="secondary"
            icon={<FileImage className="h-5 w-5" />}
            onClick={() => fileRef.current?.click()}
            className="sm:flex-1"
          >
            {t.verify.chooseFile}
          </Button>
        </div>
      </div>

      {error && <ErrorPanel error={error} onReset={() => setError(null)} />}

      {(orders.length > 0 || orderRef) && (
        <Card className="p-5">
          <Label htmlFor="order" hint={t.verify.orderHint}>
            {t.verify.bindOrder}
          </Label>
          <Select id="order" value={orderRef} onChange={(e) => setOrderRef(e.target.value)}>
            <option value="">{t.verify.noOrder}</option>
            {orderRef && !selectedOrder && <option value={orderRef}>{orderRef}</option>}
            {orders.map((o) => (
              <option key={o.order_ref} value={o.order_ref}>
                {o.order_ref} · {formatINR(o.amount)}
              </option>
            ))}
          </Select>
        </Card>
      )}

      <Card>
        <div className="border-b border-line px-5 py-4">
          <h2 className="text-sm font-semibold text-ink">{t.verify.samplesTitle}</h2>
          <p className="mt-0.5 text-xs text-muted">{t.verify.samplesHint}</p>
        </div>
        <div className="p-3">
          {samples === null ? (
            <div className="grid gap-2 sm:grid-cols-2">
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-16" />
              ))}
            </div>
          ) : samples.length === 0 ? (
            <p className="px-2 py-4 text-sm text-muted">{t.verify.samplesEmpty}</p>
          ) : (
            <ul className="grid gap-2 sm:grid-cols-2">
              {samples.map((s) => (
                <li key={s.key}>
                  <button
                    type="button"
                    onClick={() => runSample(s.key)}
                    className="flex w-full items-start gap-3 rounded-xl border border-line px-4 py-3 text-left transition-colors hover:border-line-strong hover:bg-paper"
                  >
                    <ScanSearch className="mt-0.5 h-4 w-4 shrink-0 text-muted" aria-hidden />
                    <span className="min-w-0">
                      <span className="block text-sm font-medium text-ink">{s.label}</span>
                      <span className="block text-xs text-muted">{s.description}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>

      <section aria-labelledby="layers" className="pt-2">
        <h2 id="layers" className="mb-3 text-sm font-semibold text-ink">
          {t.verify.whatWeCheck}
        </h2>
        <div className="grid gap-3 sm:grid-cols-3">
          {[
            { icon: ScanSearch, title: t.verify.layer1, body: t.verify.layer1Body },
            { icon: ListChecks, title: t.verify.layer2, body: t.verify.layer2Body },
            { icon: Landmark, title: t.verify.layer3, body: t.verify.layer3Body },
          ].map(({ icon: Icon, title, body }, i) => (
            <div key={title} className="rounded-xl border border-line bg-surface p-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-ink">
                <span className="tabular text-xs text-muted">0{i + 1}</span>
                <Icon className="h-4 w-4 text-accent" aria-hidden />
                {title}
              </div>
              <p className="mt-1.5 text-sm text-muted">{body}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense
      fallback={
        <div className="flex justify-center py-24">
          <Spinner />
        </div>
      }
    >
      <VerifyPage />
    </Suspense>
  );
}
