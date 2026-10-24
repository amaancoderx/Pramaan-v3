import type { Verdict } from "./api";

export function formatINR(value: number | null | undefined, opts: { decimals?: boolean } = {}): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: opts.decimals === false ? 0 : 2,
    maximumFractionDigits: opts.decimals === false ? 0 : 2,
  }).format(value);
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  // Backend timestamps are UTC; treat naive ISO strings as UTC.
  const normalized = /[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`;
  const d = new Date(normalized);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}

export function formatDay(date: string): string {
  const d = new Date(`${date}T00:00:00`);
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

export const APP_LABELS: Record<string, string> = {
  gpay: "Google Pay",
  phonepe: "PhonePe",
  paytm: "Paytm",
  bhim: "BHIM",
  fampay: "FamPay / FamApp",
  amazonpay: "Amazon Pay",
  whatsapppay: "WhatsApp Pay",
  mobikwik: "MobiKwik",
  cred: "CRED Pay",
  navi: "Navi",
  payzapp: "PayZapp",
  freecharge: "Freecharge",
  supermoney: "super.money",
  generic: "Other UPI",
};

export function appLabel(key: string | null | undefined): string {
  if (!key) return "-";
  return APP_LABELS[key] ?? key;
}

export const VERDICTS: Verdict[] = ["CONFIRMED", "LIKELY GENUINE", "SUSPICIOUS", "LIKELY FAKE"];

export const VERDICT_STYLE: Record<Verdict, { solid: string; soft: string; text: string; ring: string; hex: string }> = {
  CONFIRMED: { solid: "bg-confirmed", soft: "bg-confirmed-soft", text: "text-confirmed", ring: "ring-confirmed/30", hex: "#0F7B4F" },
  "LIKELY GENUINE": { solid: "bg-genuine", soft: "bg-genuine-soft", text: "text-genuine", ring: "ring-genuine/30", hex: "#2563A8" },
  SUSPICIOUS: { solid: "bg-suspicious", soft: "bg-suspicious-soft", text: "text-suspicious", ring: "ring-suspicious/30", hex: "#B26B00" },
  "LIKELY FAKE": { solid: "bg-fake", soft: "bg-fake-soft", text: "text-fake", ring: "ring-fake/30", hex: "#C2302B" },
};

export function verdictStyle(v: string) {
  return VERDICT_STYLE[v as Verdict] ?? VERDICT_STYLE.SUSPICIOUS;
}

export function riskColor(score: number): string {
  if (score >= 50) return "#C2302B";
  if (score >= 25) return "#B26B00";
  return "#0F7B4F";
}

export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      resolve(result.includes(",") ? result.split(",")[1] : result);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}
