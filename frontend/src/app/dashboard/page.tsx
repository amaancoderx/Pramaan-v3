"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CheckCheck, ChevronLeft, ChevronRight, Copy, Inbox, Search } from "lucide-react";
import { ApiError, DashboardStats, getDashboardStats, getHistory, HistoryPage, Verdict } from "@/lib/api";
import { useLanguage } from "@/context/LanguageContext";
import { Alert, Button, Card, EmptyState, Input, PageHeader, Select, Skeleton } from "@/components/ui";
import { VerdictChip } from "@/components/Chips";
import { APP_LABELS, appLabel, formatDateTime, formatDay, formatINR, VERDICTS } from "@/lib/format";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 20;

function Kpi({ label, value, hint, tone }: { label: string; value: React.ReactNode; hint?: string; tone?: string }) {
  return (
    <Card className="p-4 sm:p-5">
      <p className="text-xs font-medium text-muted">{label}</p>
      <p className={cn("tabular mt-2 text-2xl font-semibold tracking-tight text-ink", tone)}>{value}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </Card>
  );
}

function Trend({ data }: { data: DashboardStats["trend"] }) {
  const { t } = useLanguage();
  const max = Math.max(1, ...data.map((d) => d.total));
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">{t.dashboard.trend}</h2>
        <div className="flex items-center gap-4 text-xs text-muted">
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-ink/15" aria-hidden />
            {t.dashboard.trendTotal}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-fake" aria-hidden />
            {t.dashboard.trendFlagged}
          </span>
        </div>
      </div>
      <div className="mt-4 flex h-32 items-end gap-1 sm:gap-1.5" role="img" aria-label={t.dashboard.trend}>
        {data.map((d) => (
          <div key={d.date} className="group relative flex h-full flex-1 flex-col justify-end" title={`${formatDay(d.date)}: ${d.total} / ${d.flagged}`}>
            <div className="relative w-full rounded-t-[3px] bg-ink/15" style={{ height: `${(d.total / max) * 100}%`, minHeight: d.total ? 3 : 0 }}>
              <div className="absolute inset-x-0 bottom-0 rounded-t-[3px] bg-fake" style={{ height: d.total ? `${(d.flagged / d.total) * 100}%` : 0 }} />
            </div>
          </div>
        ))}
      </div>
      <div className="mt-2 flex justify-between text-2xs text-muted">
        <span>{data[0] ? formatDay(data[0].date) : ""}</span>
        <span>{data.length ? formatDay(data[data.length - 1].date) : ""}</span>
      </div>
    </Card>
  );
}

export default function DashboardPage() {
  const { t } = useLanguage();
  const router = useRouter();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [page, setPage] = useState<HistoryPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [verdict, setVerdict] = useState<Verdict | "">("");
  const [app, setApp] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    const id = window.setTimeout(() => {
      setSearch(searchInput.trim());
      setOffset(0);
    }, 300);
    return () => window.clearTimeout(id);
  }, [searchInput]);

  const loadStats = useCallback(() => {
    getDashboardStats()
      .then(setStats)
      .catch(() => setStats(null));
  }, []);

  const loadHistory = useCallback(() => {
    setLoading(true);
    setError(null);
    getHistory({ search, verdict: verdict || undefined, app: app || undefined, limit: PAGE_SIZE, offset })
      .then(setPage)
      .catch((err) => setError(err instanceof ApiError ? err.message : t.dashboard.error))
      .finally(() => setLoading(false));
  }, [search, verdict, app, offset, t.dashboard.error]);

  useEffect(() => loadStats(), [loadStats]);
  useEffect(() => loadHistory(), [loadHistory]);

  const filtered = !!(search || verdict || app);
  const items = page?.items ?? [];
  const total = page?.total ?? 0;

  return (
    <div>
      <PageHeader title={t.dashboard.title} subtitle={t.dashboard.subtitle} />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        {stats ? (
          <>
            <Kpi label={t.dashboard.checks} value={stats.total_checks} />
            <Kpi label={t.dashboard.confirmed} value={stats.confirmed_count} tone="text-confirmed" />
            <Kpi label={t.dashboard.suspicious} value={stats.suspicious_count} tone="text-suspicious" />
            <Kpi label={t.dashboard.fake} value={stats.fake_count} tone="text-fake" />
            <Kpi label={t.dashboard.reused} value={stats.reused_count} />
            <Kpi label={t.dashboard.saved} value={formatINR(stats.rupees_saved, { decimals: false })} hint={t.dashboard.savedHint} />
          </>
        ) : (
          Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-[92px] rounded-2xl" />)
        )}
      </div>

      {stats && stats.trend.length > 0 && (
        <div className="mt-4">
          <Trend data={stats.trend} />
        </div>
      )}

      <Card className="mt-6">
        <div className="flex flex-col gap-3 border-b border-line p-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="no-scrollbar -mx-1 flex gap-1.5 overflow-x-auto px-1" role="group" aria-label={t.dashboard.colVerdict}>
            {(["", ...VERDICTS] as const).map((v) => (
              <button
                key={v || "all"}
                type="button"
                aria-pressed={verdict === v}
                onClick={() => {
                  setVerdict(v);
                  setOffset(0);
                }}
                className={cn(
                  "h-9 shrink-0 rounded-lg px-3 text-sm font-medium transition-colors",
                  verdict === v ? "bg-ink text-white" : "bg-paper text-muted hover:text-ink"
                )}
              >
                {v ? t.verdict[v] : t.dashboard.all}
              </button>
            ))}
          </div>
          <div className="flex gap-2">
            <Select
              aria-label={t.dashboard.colApp}
              value={app}
              onChange={(e) => {
                setApp(e.target.value);
                setOffset(0);
              }}
              className="h-10 w-36"
            >
              <option value="">{t.dashboard.allApps}</option>
              {Object.entries(APP_LABELS).map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </Select>
            <div className="relative flex-1 lg:w-64">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden />
              <Input
                type="search"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder={t.dashboard.search}
                aria-label={t.dashboard.search}
                className="h-10 pl-9"
              />
            </div>
          </div>
        </div>

        {error ? (
          <div className="p-4">
            <Alert tone="danger" title={t.dashboard.error}>
              <p>{error}</p>
              <Button variant="secondary" size="sm" className="mt-2" onClick={loadHistory}>
                {t.dashboard.retry}
              </Button>
            </Alert>
          </div>
        ) : loading && !page ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-12" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            icon={<Inbox className="h-5 w-5" />}
            title={filtered ? t.dashboard.emptyFiltered : t.dashboard.empty}
            body={filtered ? undefined : t.dashboard.emptyBody}
            action={
              !filtered && (
                <Link href="/" className="inline-flex h-11 items-center rounded-xl bg-ink px-4 text-sm font-medium text-white">
                  {t.dashboard.startCheck}
                </Link>
              )
            }
          />
        ) : (
          <div className={cn(loading && "opacity-60 transition-opacity")}>
            <table className="hidden w-full text-sm md:table">
              <thead>
                <tr className="border-b border-line text-left text-xs text-muted">
                  <th className="px-4 py-3 font-medium">{t.dashboard.colCheck}</th>
                  <th className="px-4 py-3 font-medium">{t.dashboard.colVerdict}</th>
                  <th className="px-4 py-3 text-right font-medium">{t.dashboard.colAmount}</th>
                  <th className="px-4 py-3 font-medium">{t.dashboard.colUtr}</th>
                  <th className="px-4 py-3 font-medium">{t.dashboard.colApp}</th>
                  <th className="px-4 py-3 font-medium">{t.dashboard.colTime}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {items.map((item) => (
                  <tr
                    key={item.id}
                    onClick={() => router.push(`/checks/${encodeURIComponent(item.id)}`)}
                    className="cursor-pointer hover:bg-paper"
                  >
                    <td className="px-4 py-3">
                      <Link href={`/checks/${encodeURIComponent(item.id)}`} className="font-mono text-xs font-medium text-ink hover:underline" onClick={(e) => e.stopPropagation()}>
                        {item.id}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <VerdictChip verdict={item.verdict} />
                        {item.is_reused && (
                          <span className="inline-flex items-center gap-1 text-xs text-fake">
                            <Copy className="h-3 w-3" aria-hidden />
                            {t.dashboard.reusedTag}
                          </span>
                        )}
                        {item.handled && <CheckCheck className="h-4 w-4 text-confirmed" aria-label={t.dashboard.handled} />}
                      </div>
                    </td>
                    <td className="tabular px-4 py-3 text-right font-medium">{formatINR(item.amount)}</td>
                    <td className="px-4 py-3 font-mono text-xs text-muted">{item.utr ?? "-"}</td>
                    <td className="px-4 py-3 text-muted">{appLabel(item.payment_app)}</td>
                    <td className="px-4 py-3 text-muted">{formatDateTime(item.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <ul className="divide-y divide-line md:hidden">
              {items.map((item) => (
                <li key={item.id}>
                  <Link href={`/checks/${encodeURIComponent(item.id)}`} className="flex items-center justify-between gap-3 px-4 py-3 active:bg-paper">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <VerdictChip verdict={item.verdict} />
                        {item.is_reused && <span className="text-xs text-fake">{t.dashboard.reusedTag}</span>}
                        {item.handled && <CheckCheck className="h-4 w-4 text-confirmed" aria-label={t.dashboard.handled} />}
                      </div>
                      <p className="mt-1 truncate font-mono text-xs text-muted">{item.utr ?? item.id}</p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="tabular text-sm font-semibold">{formatINR(item.amount)}</p>
                      <p className="text-xs text-muted">{formatDateTime(item.created_at)}</p>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>

            <div className="flex items-center justify-between gap-3 border-t border-line px-4 py-3 text-sm">
              <span className="tabular text-muted">
                {t.dashboard.showing} {offset + 1}-{Math.min(offset + PAGE_SIZE, total)} {t.dashboard.of} {total}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  icon={<ChevronLeft className="h-4 w-4" />}
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                  aria-label={t.dashboard.prev}
                >
                  <span className="hidden sm:inline">{t.dashboard.prev}</span>
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={offset + PAGE_SIZE >= total}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                  aria-label={t.dashboard.next}
                >
                  <span className="hidden sm:inline">{t.dashboard.next}</span>
                  <ChevronRight className="h-4 w-4" aria-hidden />
                </Button>
              </div>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
