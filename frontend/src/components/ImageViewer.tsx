"use client";

import React, { forwardRef, useState } from "react";
import { Eye, Flame, ImageOff, ScanLine } from "lucide-react";
import type { BBox, FieldKey, Verification } from "@/lib/api";
import { useLanguage } from "@/context/LanguageContext";
import { cn } from "@/lib/utils";

export type ViewMode = "original" | "heatmap";

export interface ViewerFocus {
  field?: string | null;
  region?: BBox | null;
}

const OVERLAY_FIELDS: FieldKey[] = ["amount", "utr", "timestamp", "receiver_upi_id"];

interface Props {
  check: Verification;
  mode: ViewMode;
  onModeChange: (m: ViewMode) => void;
  focus: ViewerFocus | null;
}

function pct(box: BBox, w: number, h: number): React.CSSProperties {
  return {
    left: `${(box.x / w) * 100}%`,
    top: `${(box.y / h) * 100}%`,
    width: `${(box.width / w) * 100}%`,
    height: `${(box.height / h) * 100}%`,
  };
}

export const ImageViewer = forwardRef<HTMLDivElement, Props>(function ImageViewer({ check, mode, onModeChange, focus }, ref) {
  const { t } = useLanguage();
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [showBoxes, setShowBoxes] = useState(true);
  const [failed, setFailed] = useState(false);

  const w = check.image_width || natural?.w || 0;
  const h = check.image_height || natural?.h || 0;
  const hasImage = check.image_available && !!check.image_url && !failed;
  const src = mode === "heatmap" && check.heatmap_url ? check.heatmap_url : check.image_url;

  const fieldBoxes = OVERLAY_FIELDS.map((key) => ({ key, field: check.extracted_data[key] })).filter(
    (b) => b.field?.bbox && b.field.value
  );
  const regionBoxes = check.reasons
    .filter((r) => r.region && r.severity !== "INFO")
    .map((r, i) => ({ key: `${r.code}-${i}`, region: r.region as BBox, title: r.title }));

  return (
    <div ref={ref} className="scroll-mt-24 overflow-hidden rounded-2xl border border-line bg-surface shadow-card">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-3 py-2.5">
        <div className="inline-flex rounded-lg bg-paper p-1" role="group" aria-label="View">
          <button
            type="button"
            onClick={() => onModeChange("original")}
            aria-pressed={mode === "original"}
            className={cn(
              "inline-flex h-9 items-center gap-1.5 rounded-md px-3 text-sm font-medium",
              mode === "original" ? "bg-surface text-ink shadow-card" : "text-muted hover:text-ink"
            )}
          >
            <Eye className="h-4 w-4" aria-hidden />
            {t.result.original}
          </button>
          <button
            type="button"
            onClick={() => onModeChange("heatmap")}
            disabled={!check.heatmap_url || !hasImage}
            aria-pressed={mode === "heatmap"}
            className={cn(
              "inline-flex h-9 items-center gap-1.5 rounded-md px-3 text-sm font-medium disabled:opacity-40",
              mode === "heatmap" ? "bg-surface text-ink shadow-card" : "text-muted hover:text-ink"
            )}
          >
            <Flame className="h-4 w-4" aria-hidden />
            {t.result.heatmap}
          </button>
        </div>
        <button
          type="button"
          onClick={() => setShowBoxes((v) => !v)}
          aria-pressed={showBoxes}
          disabled={!hasImage}
          className={cn(
            "inline-flex h-9 items-center gap-1.5 rounded-lg border px-3 text-sm font-medium disabled:opacity-40",
            showBoxes ? "border-accent/40 bg-accent-soft text-accent-ink" : "border-line text-muted hover:text-ink"
          )}
        >
          <ScanLine className="h-4 w-4" aria-hidden />
          {t.result.highlights}
        </button>
      </div>

      <div className="flex min-h-[320px] items-center justify-center bg-ink-2/[0.04] p-3 sm:p-4">
        {hasImage && src ? (
          <div className="relative inline-block max-w-full">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={src}
              alt={t.result.original}
              className="block max-h-[640px] w-auto max-w-full rounded-lg border border-line"
              onLoad={(e) => setNatural({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
              onError={() => setFailed(true)}
            />
            {showBoxes && w > 0 && h > 0 && (
              <div className="pointer-events-none absolute inset-0">
                {fieldBoxes.map(({ key, field }) => {
                  const focused = focus?.field === key;
                  return (
                    <div
                      key={key}
                      className={cn(
                        "absolute rounded-[3px] border-2",
                        field.is_valid ? "border-confirmed/80" : "border-fake bg-fake/10",
                        focused && "ring-4 ring-accent/60"
                      )}
                      style={pct(field.bbox as BBox, w, h)}
                    >
                      <span
                        className={cn(
                          "absolute -top-5 left-0 whitespace-nowrap rounded px-1 text-[10px] font-semibold leading-4 text-white",
                          field.is_valid ? "bg-confirmed" : "bg-fake"
                        )}
                      >
                        {t.fields[key]}
                      </span>
                    </div>
                  );
                })}
                {regionBoxes.map(({ key, region, title }) => {
                  const focused =
                    focus?.region && focus.region.x === region.x && focus.region.y === region.y && focus.region.width === region.width;
                  return (
                    <div
                      key={key}
                      title={title}
                      className={cn("absolute rounded-[3px] border-2 border-dashed border-suspicious", focused && "ring-4 ring-accent/60")}
                      style={pct(region, w, h)}
                    />
                  );
                })}
                {focus?.region && !regionBoxes.some((b) => b.region === focus.region) && (
                  <div className="absolute rounded-[3px] border-2 border-accent ring-4 ring-accent/40" style={pct(focus.region, w, h)} />
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="flex max-w-xs flex-col items-center py-12 text-center text-sm text-muted">
            <ImageOff className="mb-3 h-8 w-8" aria-hidden />
            {t.result.imageDeleted}
          </div>
        )}
      </div>

      {mode === "heatmap" && hasImage && (
        <p className="flex items-start gap-2 border-t border-line bg-paper px-4 py-3 text-xs text-muted">
          <Flame className="mt-0.5 h-3.5 w-3.5 shrink-0 text-suspicious" aria-hidden />
          {t.result.heatmapHint}
        </p>
      )}
    </div>
  );
});
