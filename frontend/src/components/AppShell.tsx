"use client";

import React, { useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { History, LogOut, QrCode, ScanLine, Settings, Languages, Lock } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useLanguage } from "@/context/LanguageContext";
import { LogoMark } from "./Logo";
import { OfflineBanner } from "./OfflineBanner";
import { Spinner } from "./ui";
import { cn } from "@/lib/utils";

const PUBLIC_PREFIXES = ["/login", "/benchmark", "/verify/", "/offline"];

function isPublic(path: string) {
  return PUBLIC_PREFIXES.some((p) => path === p || path.startsWith(p));
}

function useNavItems() {
  const { t } = useLanguage();
  return [
    { href: "/", label: t.nav.verify, icon: ScanLine },
    { href: "/dashboard", label: t.nav.dashboard, icon: History },
    { href: "/qr", label: t.nav.qr, icon: QrCode },
    { href: "/settings", label: t.nav.settings, icon: Settings },
  ];
}

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/" || pathname.startsWith("/checks");
  return pathname.startsWith(href);
}

function LanguageToggle({ compact = false }: { compact?: boolean }) {
  const { lang, setLang, t } = useLanguage();
  return (
    <button
      type="button"
      onClick={() => setLang(lang === "en" ? "hi" : "en")}
      aria-label={t.nav.languageLabel}
      className={cn(
        "inline-flex h-10 items-center gap-1.5 rounded-lg px-3 text-sm font-medium text-white/85 hover:bg-white/10 hover:text-white",
        compact && "px-2.5"
      )}
    >
      <Languages className="h-4 w-4" aria-hidden />
      <span>{t.nav.language}</span>
    </button>
  );
}

function Header() {
  const pathname = usePathname();
  const router = useRouter();
  const { merchant, status, logout } = useAuth();
  const { t } = useLanguage();
  const items = useNavItems();
  const authed = status === "authenticated";

  return (
    <header className="sticky top-0 z-40 bg-ink text-white">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-4 px-4 sm:h-16 sm:px-6">
        <Link href={authed ? "/" : "/login"} className="flex items-center gap-2.5 rounded-lg">
          <LogoMark className="h-8 w-8" />
          <span className="text-[17px] font-semibold tracking-tight">{t.appName}</span>
        </Link>

        {authed && (
          <nav className="ml-4 hidden items-center gap-1 md:flex" aria-label="Main">
            {items.map(({ href, label, icon: Icon }) => (
              <Link
                key={href}
                href={href}
                aria-current={isActive(pathname, href) ? "page" : undefined}
                className={cn(
                  "inline-flex h-10 items-center gap-2 rounded-lg px-3 text-sm font-medium transition-colors",
                  isActive(pathname, href) ? "bg-white/10 text-white" : "text-white/70 hover:bg-white/5 hover:text-white"
                )}
              >
                <Icon className="h-4 w-4" aria-hidden />
                {label}
              </Link>
            ))}
          </nav>
        )}

        <div className="ml-auto flex items-center gap-1">
          {authed && merchant && (
            <div className="mr-2 hidden text-right leading-tight lg:block">
              <p className="text-sm font-medium">{merchant.name}</p>
              <p className="font-mono text-xs text-white/60">{merchant.registered_upi_id}</p>
            </div>
          )}
          <LanguageToggle />
          {authed && (
            <button
              type="button"
              onClick={() => {
                logout();
                router.replace("/login");
              }}
              aria-label={t.nav.logout}
              title={t.nav.logout}
              className="inline-flex h-10 w-10 items-center justify-center rounded-lg text-white/75 hover:bg-white/10 hover:text-white"
            >
              <LogOut className="h-4 w-4" aria-hidden />
            </button>
          )}
        </div>
      </div>
    </header>
  );
}

function BottomNav() {
  const pathname = usePathname();
  const items = useNavItems();
  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-surface md:hidden"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      <ul className="grid grid-cols-4">
        {items.map(({ href, label, icon: Icon }) => {
          const active = isActive(pathname, href);
          return (
            <li key={href}>
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex h-16 flex-col items-center justify-center gap-1 text-xs font-medium",
                  active ? "text-ink" : "text-muted"
                )}
              >
                <Icon className={cn("h-5 w-5", active && "text-accent")} aria-hidden />
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function Footer({ withBottomNav }: { withBottomNav: boolean }) {
  const { t } = useLanguage();
  return (
    <footer className={cn("border-t border-line bg-paper", withBottomNav && "pb-20 md:pb-0")}>
      <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-6 text-xs text-muted sm:px-6 md:flex-row md:items-center md:justify-between">
        <p className="flex items-start gap-2">
          <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          <span>
            {t.footer.privacy} {t.footer.disclaimer}
          </span>
        </p>
        <div className="flex shrink-0 items-center gap-4">
          <Link href="/benchmark" className="hover:text-ink">
            {t.nav.benchmark}
          </Link>
          <span>{t.footer.credit}</span>
        </div>
      </div>
    </footer>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/";
  const router = useRouter();
  const { status } = useAuth();
  const publicRoute = isPublic(pathname);
  const authed = status === "authenticated";

  useEffect(() => {
    if (status === "anonymous" && !publicRoute) {
      const next = typeof window !== "undefined" ? window.location.pathname + window.location.search : pathname;
      router.replace(`/login?next=${encodeURIComponent(next)}`);
    }
  }, [status, publicRoute, pathname, router]);

  const blocked = !publicRoute && status !== "authenticated";

  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <OfflineBanner />
      <main className={cn("mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 sm:py-8", authed && "pb-24 md:pb-8")}>
        {blocked ? (
          <div className="flex justify-center py-24">
            <Spinner />
          </div>
        ) : (
          children
        )}
      </main>
      <Footer withBottomNav={authed} />
      {authed && <BottomNav />}
    </div>
  );
}
