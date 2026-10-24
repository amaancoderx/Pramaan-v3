"use client";

import React, { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Check } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useLanguage } from "@/context/LanguageContext";
import { Alert, Button, Card, Input, Label, Spinner } from "@/components/ui";
import { ApiError, wakeBackend } from "@/lib/api";
import { cn } from "@/lib/utils";

const DEMO_EMAIL = "merchant@pramaan.local";
const DEMO_PASSWORD = "shopkeeper123";

function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/login")) return "/";
  return raw;
}

function LoginForm() {
  const { t } = useLanguage();
  const { login, register, status } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));

  const [mode, setMode] = useState<"signin" | "register">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [upi, setUpi] = useState("");
  const [receiverName, setReceiverName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (status === "authenticated") router.replace(next);
  }, [status, next, router]);

  // Start waking a sleeping API while the user types.
  useEffect(() => {
    wakeBackend();
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (mode === "register" && password.length < 8) {
      setError(t.auth.passwordShort);
      return;
    }
    setBusy(true);
    try {
      if (mode === "signin") await login(email.trim(), password);
      else await register({ email: email.trim(), password, name: name.trim(), registered_upi_id: upi.trim(), registered_receiver_name: receiverName.trim() });
      router.replace(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t.common.error);
    } finally {
      setBusy(false);
    }
  };

  const useDemo = async () => {
    setMode("signin");
    setEmail(DEMO_EMAIL);
    setPassword(DEMO_PASSWORD);
    setError(null);
    setBusy(true);
    try {
      await login(DEMO_EMAIL, DEMO_PASSWORD);
      router.replace(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t.common.error);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto grid max-w-5xl items-start gap-10 py-4 md:grid-cols-2 md:py-10">
      <section className="hidden md:block">
        <h1 className="text-3xl font-semibold leading-tight tracking-tight text-ink">{t.auth.headline}</h1>
        <p className="mt-4 max-w-md text-base text-muted">{t.auth.sub}</p>
        <ul className="mt-8 space-y-4">
          {[t.auth.point1, t.auth.point2, t.auth.point3].map((p) => (
            <li key={p} className="flex items-start gap-3 text-sm text-ink">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent-ink">
                <Check className="h-3.5 w-3.5" aria-hidden />
              </span>
              {p}
            </li>
          ))}
        </ul>
      </section>

      <Card className="w-full p-6 sm:p-8">
        <div className="mb-6 grid grid-cols-2 rounded-xl bg-paper p-1" role="tablist">
          {(["signin", "register"] as const).map((m) => (
            <button
              key={m}
              type="button"
              role="tab"
              aria-selected={mode === m}
              onClick={() => {
                setMode(m);
                setError(null);
              }}
              className={cn(
                "h-10 rounded-lg text-sm font-medium transition-colors",
                mode === m ? "bg-surface text-ink shadow-card" : "text-muted hover:text-ink"
              )}
            >
              {m === "signin" ? t.auth.signIn : t.auth.createAccount}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="space-y-4">
          {mode === "register" && (
            <>
            <div>
              <Label htmlFor="name">{t.auth.shopName}</Label>
              <Input id="name" required value={name} onChange={(e) => setName(e.target.value)} autoComplete="organization" />
              <p className="mt-1 text-xs text-muted">Use the exact store display name you want to register.</p>
            </div>
            <div>
              <Label htmlFor="receiverName">{t.auth.receiverName}</Label>
              <Input id="receiverName" required minLength={2} maxLength={100} value={receiverName}
                onChange={(e) => setReceiverName(e.target.value)} autoComplete="name" />
              <p className="mt-1 text-xs text-muted">{t.auth.receiverNameHint}</p>
            </div>
            </>
          )}
          <div>
            <Label htmlFor="email">{t.auth.email}</Label>
            <Input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              inputMode="email"
            />
          </div>
          <div>
            <Label htmlFor="password">{t.auth.password}</Label>
            <Input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "signin" ? "current-password" : "new-password"}
            />
          </div>
          {mode === "register" && (
            <div>
              <Label htmlFor="upi" hint={t.auth.upiHint}>
                {t.auth.upiId}
              </Label>
              <Input
                id="upi"
                required
                value={upi}
                onChange={(e) => setUpi(e.target.value)}
                placeholder="yourshop@okbank"
                className="font-mono"
                autoCapitalize="none"
                autoCorrect="off"
              />
            </div>
          )}

          {error && <Alert tone="danger">{error}</Alert>}

          <Button type="submit" size="lg" className="w-full" loading={busy}>
            {mode === "signin" ? t.auth.submitSignIn : t.auth.submitRegister}
          </Button>
        </form>

        {mode === "signin" && (
          <div className="mt-6 flex flex-col gap-3 rounded-xl border border-line bg-paper p-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-medium text-ink">{t.auth.demoTitle}</p>
              <p className="font-mono text-xs text-muted">{t.auth.demoBody}</p>
            </div>
            <Button variant="secondary" size="sm" onClick={useDemo} disabled={busy}>
              {t.auth.useDemo}
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="flex justify-center py-24">
          <Spinner />
        </div>
      }
    >
      <LoginForm />
    </Suspense>
  );
}
