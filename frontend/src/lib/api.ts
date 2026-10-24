export const TOKEN_KEY = "pramaan_token";

export type Verdict = "CONFIRMED" | "LIKELY GENUINE" | "SUSPICIOUS" | "LIKELY FAKE";
export type Severity = "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type Layer = "forensics" | "rules" | "ground_truth" | "duplicate";
export type Strictness = "lenient" | "standard" | "strict";
export type PaymentApp = "gpay" | "phonepe" | "paytm" | "bhim" | "generic";

export interface BBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Field {
  value: string | null;
  confidence: number;
  bbox: BBox | null;
  is_valid: boolean;
  corrected: boolean;
}

export interface ExtractedData {
  payment_app: PaymentApp | string;
  document_type?: "transaction_detail" | "history_list" | "unknown";
  amount: Field;
  utr: Field;
  timestamp: Field;
  sender: Field;
  receiver: Field;
  receiver_upi_id: Field;
  status: Field;
  amount_in_words: Field;
  status_bar_time: Field;
}

export type FieldKey = Exclude<keyof ExtractedData, "payment_app" | "document_type">;

export type EvidenceType = "heatmap" | "field" | "metadata" | "sms" | "duplicate" | "order";

export interface Reason {
  code: string;
  severity: Severity;
  layer: Layer;
  title: string;
  message: string;
  field: string | null;
  penalty: number;
  evidence_type: EvidenceType | null;
  evidence_value: unknown;
  region: BBox | null;
}

export interface PassedCheck {
  code: string;
  layer: Layer;
  title: string;
}

export interface GroundTruth {
  status: "NONE" | "SMS_MATCHED" | "SMS_MISMATCH";
  sms_amount: number | null;
  sms_utr: string | null;
  bank: string | null;
  account_masked: string | null;
  amount_matched: boolean | null;
  utr_matched: boolean | null;
  message: string | null;
}

export interface OrderBinding {
  order_ref: string;
  amount: number;
  status: "open" | "paid";
  matched_by: "reference" | "amount" | "none";
}

export interface Verification {
  id: string;
  verdict: Verdict;
  risk_score: number;
  final_verdict_reason: string;
  reasons: Reason[];
  passed_checks: PassedCheck[];
  payment_app: string;
  image_url: string | null;
  heatmap_url: string | null;
  image_available: boolean;
  image_width: number | null;
  image_height: number | null;
  report_url: string;
  extracted_data: ExtractedData;
  is_reused: boolean;
  reused_first_seen: { id: string; seen_at: string; same_merchant: boolean } | null;
  ground_truth: GroundTruth;
  order: OrderBinding | null;
  layer_scores: { forensics: number; rules: number; ground_truth: number; duplicate: number };
  strictness: string;
  check_mode?: CheckMode;
  handled: boolean;
  handled_at: string | null;
  created_at: string;
  processing_time_seconds: number;
}

export interface PublicVerification {
  id: string;
  verdict: Verdict;
  risk_score: number;
  amount: number | null;
  utr_masked: string;
  payment_app: string;
  checked_at: string;
  merchant_name: string;
  ground_truth_status: "NONE" | "SMS_MATCHED" | "SMS_MISMATCH";
}

export interface Merchant {
  id: number;
  email: string;
  name: string;
  registered_upi_id: string;
  registered_receiver_name: string | null;
  allowed_window_minutes: number;
  strictness: Strictness;
  api_key: string | null;
  created_at: string;
}

export interface Token {
  access_token: string;
  token_type: "bearer";
  merchant: Merchant;
}

export interface DashboardStats {
  total_checks: number;
  confirmed_count: number;
  likely_genuine_count: number;
  suspicious_count: number;
  fake_count: number;
  reused_count: number;
  handled_count: number;
  rupees_saved: number;
  total_volume: number;
  trend: { date: string; total: number; flagged: number }[];
}

export interface HistoryItem {
  id: string;
  verdict: Verdict;
  risk_score: number;
  amount: number | null;
  utr: string | null;
  payment_app: string;
  is_reused: boolean;
  handled: boolean;
  created_at: string;
  image_available: boolean;
}

export interface HistoryPage {
  total: number;
  limit: number;
  offset: number;
  items: HistoryItem[];
}

export interface Order {
  order_ref: string;
  amount: number;
  status: "open" | "paid";
  upi_uri: string;
  qr_image_data_url: string;
  merchant_upi_id: string;
  merchant_name: string;
  created_at: string;
  verification_id: string | null;
}

export interface DemoSample {
  key: string;
  label: string;
  description: string;
  expected: string;
}

export interface BenchmarkSample {
  id: string;
  filename?: string;
  label: "clean" | "tampered" | string;
  tamper_type: string;
  verdict: Verdict | string;
  risk_score: number;
  reasons?: string[];
  top_reason?: string | null;
  processing_time?: number;
  predicted_tampered?: boolean;
}

export interface BenchmarkResults {
  status?: string;
  message?: string;
  dataset_name?: string;
  description?: string;
  generated_at?: string;
  evaluated_at?: string;
  decision_rule?: string;
  total_samples?: number;
  clean_samples?: number;
  tampered_samples?: number;
  confusion_matrix?: {
    true_positives: number;
    true_negatives: number;
    false_positives: number;
    false_negatives: number;
  };
  metrics?: {
    accuracy: number;
    precision: number;
    recall: number;
    f1_score: number;
    avg_latency_seconds: number;
    max_latency_seconds?: number;
  };
  per_tamper?: Record<string, { detected: number; total: number }>;
  samples?: BenchmarkSample[];
}

export interface Corrections {
  amount?: string | null;
  utr?: string | null;
  timestamp?: string | null;
  receiver?: string | null;
  receiver_upi_id?: string | null;
  status?: string | null;
}

export class ApiError extends Error {
  status: number;
  code: string | null;

  constructor(message: string, status: number, code: string | null = null) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // storage unavailable (private mode); session will not persist
  }
}

type Detail = string | { code?: string; message?: string } | { msg?: string; loc?: unknown[] }[] | undefined;

function describeDetail(detail: Detail, fallback: string): { message: string; code: string | null } {
  if (!detail) return { message: fallback, code: null };
  if (typeof detail === "string") return { message: detail, code: null };
  if (Array.isArray(detail)) {
    const first = detail[0];
    return { message: first?.msg ? String(first.msg) : fallback, code: "VALIDATION_ERROR" };
  }
  return { message: detail.message || fallback, code: detail.code || null };
}

const PUBLIC_PATHS = ["/login", "/benchmark", "/verify/", "/offline"];

function handleUnauthorized() {
  setToken(null);
  if (typeof window === "undefined") return;
  const path = window.location.pathname;
  if (PUBLIC_PATHS.some((p) => path.startsWith(p))) return;
  const next = encodeURIComponent(path + window.location.search);
  window.location.replace(`/login?next=${next}`);
}

let wakeSent = 0;

// The web app's proxy gives up before a sleeping Render API boots, so wake the API by its own URL.
export function wakeBackend() {
  if (typeof window === "undefined" || !process.env.NEXT_PUBLIC_BACKEND_URL) return;
  if (Date.now() - wakeSent < 20_000) return;
  wakeSent = Date.now();
  fetch(`${backendOrigin()}/api/health`, { mode: "no-cors" }).catch(() => undefined);
}

async function request(path: string, init: RequestInit = {}, auth = true): Promise<Response> {
  const headers = new Headers(init.headers);
  if (auth) {
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }
  if (init.body && typeof init.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let res: Response;
  // A sleeping free-tier API answers 502/503/504 for up to a minute while it boots; wait it out.
  const wakeDeadline = Date.now() + 90_000;
  for (;;) {
    try {
      res = await fetch(path, { ...init, headers });
    } catch {
      const offline = typeof navigator !== "undefined" && !navigator.onLine;
      throw new ApiError(
        offline ? "You are offline. Analysis needs an internet connection." : "Could not reach the Pramaan server.",
        0,
        offline ? "OFFLINE" : "NETWORK"
      );
    }
    if (![502, 503, 504].includes(res.status) || Date.now() > wakeDeadline) break;
    wakeBackend();
    await new Promise((r) => setTimeout(r, 3_000));
  }

  if (!res.ok) {
    let detail: Detail;
    try {
      detail = (await res.json()).detail;
    } catch {
      detail = undefined;
    }
    const { message, code } = describeDetail(detail, `Request failed (${res.status})`);
    if (res.status === 401 && auth) handleUnauthorized();
    throw new ApiError(message, res.status, code ?? (res.status === 401 ? "UNAUTHORIZED" : null));
  }
  return res;
}

async function json<T>(path: string, init: RequestInit = {}, auth = true): Promise<T> {
  const res = await request(path, init, auth);
  return res.json() as Promise<T>;
}

// Auth
export const login = (email: string, password: string) =>
  json<Token>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }, false);

export const register = (data: { email: string; password: string; name: string; registered_upi_id: string; registered_receiver_name: string }) =>
  json<Token>("/api/auth/register", { method: "POST", body: JSON.stringify(data) }, false);

export const getMe = () => json<Merchant>("/api/auth/me");

// Settings
export const getSettings = () => json<Merchant>("/api/settings");

export const updateSettings = (data: Partial<Pick<Merchant, "name" | "registered_upi_id" | "registered_receiver_name" | "allowed_window_minutes" | "strictness">>) =>
  json<Merchant>("/api/settings", { method: "PUT", body: JSON.stringify(data) });

export const rotateApiKey = () => json<Merchant>("/api/settings/api-key/rotate", { method: "POST" });

// Verification
export type CheckMode = "merchant" | "authenticity";

export function analyzeScreenshot(file: File, orderRef?: string | null, mode: CheckMode = "merchant"): Promise<Verification> {
  const form = new FormData();
  form.append("file", file);
  if (orderRef) form.append("order_ref", orderRef);
  form.append("check_mode", mode);
  return json<Verification>("/api/verify/analyze", { method: "POST", body: form });
}

export const getVerification = (id: string) => json<Verification>(`/api/verify/${encodeURIComponent(id)}`);

export const submitCorrections = (id: string, corrections: Corrections) =>
  json<Verification>(`/api/verify/${encodeURIComponent(id)}/corrections`, {
    method: "POST",
    body: JSON.stringify(corrections),
  });

export const matchSms = (id: string, payload: { sms_text?: string; sms_image_base64?: string }) =>
  json<Verification>(`/api/verify/${encodeURIComponent(id)}/sms`, { method: "POST", body: JSON.stringify(payload) });

export const setHandled = (id: string, handled: boolean) =>
  json<Verification>(`/api/verify/${encodeURIComponent(id)}/handled`, {
    method: "POST",
    body: JSON.stringify({ handled }),
  });

export async function downloadReport(id: string) {
  const res = await request(`/api/verify/${encodeURIComponent(id)}/report`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `Pramaan_Report_${id}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export const getPublicVerification = (id: string) =>
  json<PublicVerification>(`/api/public/verify/${encodeURIComponent(id)}`, {}, false);

// Dashboard
export const getDashboardStats = () => json<DashboardStats>("/api/dashboard/stats");

export function getHistory(params: { search?: string; verdict?: string; app?: string; limit?: number; offset?: number }) {
  const q = new URLSearchParams();
  if (params.search) q.set("search", params.search);
  if (params.verdict) q.set("verdict", params.verdict);
  if (params.app) q.set("app", params.app);
  q.set("limit", String(params.limit ?? 20));
  q.set("offset", String(params.offset ?? 0));
  return json<HistoryPage>(`/api/dashboard/history?${q.toString()}`);
}

// Orders
export const generateOrder = (amount: number, note?: string) =>
  json<Order>("/api/qr/generate", { method: "POST", body: JSON.stringify({ amount, note: note || null }) });

export const listOrders = (status?: "open" | "paid") =>
  json<{ items: Order[] }>(`/api/qr/orders${status ? `?status=${status}` : ""}`);

// Demo samples
export const listDemoSamples = () => json<{ items: DemoSample[] }>("/api/demo/samples");

export async function fetchDemoSample(key: string): Promise<File> {
  const res = await request(`/api/demo/samples/${encodeURIComponent(key)}`);
  const blob = await res.blob();
  const type = blob.type || "image/png";
  const ext = type.includes("jpeg") ? "jpg" : type.split("/")[1] || "png";
  return new File([blob], `mock_${key}.${ext}`, { type });
}

// Public
export const getBenchmark = () => json<BenchmarkResults>("/api/benchmark/results", {}, false);

export function backendOrigin(): string {
  // Set NEXT_PUBLIC_BACKEND_URL in production (e.g. the Hugging Face Space URL) so the docs link and curl sample are right.
  const env = process.env.NEXT_PUBLIC_BACKEND_URL;
  if (env) return (env.startsWith("http") ? env : `https://${env}`).replace(/\/$/, "");
  if (typeof window === "undefined") return "http://localhost:8000";
  return `${window.location.protocol}//${window.location.hostname}:8000`;
}
