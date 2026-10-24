# Pramaan REST API

Base URL (local): `http://localhost:8000`. Interactive OpenAPI docs: `/docs` (Swagger) and `/redoc`.

The web app talks to the API through the Next.js proxy at `/api/*`, so in the browser every path below is
also reachable as `http://localhost:3000/api/...`.

## Authentication

Every merchant endpoint accepts **either**:

| Header | Used by |
| --- | --- |
| `Authorization: Bearer <jwt>` | The web app (token from `/api/auth/login`) |
| `X-API-Key: <key>` | POS / server integrations (key shown in Settings) |

Public endpoints (no auth): `/api/health`, `/api/rules`, `/api/benchmark/results`, `/api/public/verify/{id}`.

## Errors

Errors raised by Pramaan use `{"detail": {"code": "...", "message": "..."}}`.

| Status | code | When |
| --- | --- | --- |
| 401 | `UNAUTHORIZED` | Missing/invalid token or API key |
| 404 | `NOT_FOUND` | Unknown check / order |
| 409 | `EMAIL_TAKEN` | Register with an existing email |
| 413 | `FILE_TOO_LARGE` | Upload over 10 MB |
| 415 | `NOT_AN_IMAGE` | Upload is not a decodable JPG/PNG/WEBP |
| 422 | `IMAGE_QUALITY_LOW` | Blurry, tiny, or too cropped to read reliably |
| 422 | `SMS_UNREADABLE` | SMS text / screenshot has no amount or UTR |

FastAPI's own request-validation errors keep the default `{"detail": [ ... ]}` list shape.

## Endpoints

### Auth
- `POST /api/auth/register` `{email, password, name, registered_upi_id}` → `Token`
- `POST /api/auth/login` `{email, password}` → `Token`
- `GET  /api/auth/me` → `Merchant`

`Token = {access_token, token_type: "bearer", merchant: Merchant}`

`Merchant = {id, email, name, registered_upi_id, allowed_window_minutes, strictness: "lenient"|"standard"|"strict", api_key, created_at}`

### Settings
- `GET  /api/settings` → `Merchant`
- `PUT  /api/settings` `{name?, registered_upi_id?, allowed_window_minutes?, strictness?}` → `Merchant`
- `POST /api/settings/api-key/rotate` → `Merchant` (new `api_key`)

### Verification
- `POST /api/verify/analyze`, `multipart/form-data`: `file` (required), `order_ref` (optional) → `Verification`
- `GET  /api/verify/{id}` → `Verification`
- `POST /api/verify/{id}/corrections` `{amount?, utr?, timestamp?, receiver?, receiver_upi_id?, status?}` → `Verification` (re-scored)
- `POST /api/verify/{id}/sms` `{sms_text?: string, sms_image_base64?: string}` → `Verification`
- `POST /api/verify/{id}/handled` `{handled: boolean}` → `Verification`
- `GET  /api/verify/{id}/report` → `application/pdf`
- `GET  /api/public/verify/{id}` (public) → `PublicVerification`

```ts
type Verdict = "CONFIRMED" | "LIKELY GENUINE" | "SUSPICIOUS" | "LIKELY FAKE";
type Severity = "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
type Layer = "forensics" | "rules" | "ground_truth" | "duplicate";

interface BBox { x: number; y: number; width: number; height: number }   // pixels in the original image

interface Field { value: string | null; confidence: number; bbox: BBox | null; is_valid: boolean; corrected: boolean }

interface ExtractedData {
  payment_app: "gpay" | "phonepe" | "paytm" | "bhim" | "generic";
  amount: Field; utr: Field; timestamp: Field; sender: Field; receiver: Field;
  receiver_upi_id: Field; status: Field; amount_in_words: Field; status_bar_time: Field;
}

interface Reason {
  code: string; severity: Severity; layer: Layer;
  title: string; message: string;          // English, plain language
  field: string | null;                    // ExtractedData key this reason points at
  penalty: number;                         // contribution to risk score
  evidence_type: "heatmap" | "field" | "metadata" | "sms" | "duplicate" | "order" | null;
  evidence_value: any;
  region: BBox | null;                     // suspected region to highlight on the image
}

interface PassedCheck { code: string; layer: Layer; title: string }

interface Verification {
  id: string;                              // e.g. "PRM-7KQ2M9XD"
  verdict: Verdict;
  risk_score: number;                      // 0..100
  final_verdict_reason: string;
  reasons: Reason[];                       // ranked: most severe first
  passed_checks: PassedCheck[];
  payment_app: string;
  image_url: string | null;                // null once purged (24h retention)
  heatmap_url: string | null;
  image_available: boolean;
  image_width: number | null; image_height: number | null;
  report_url: string;                      // "/api/verify/{id}/report" (needs auth)
  extracted_data: ExtractedData;
  is_reused: boolean;
  reused_first_seen: { id: string; seen_at: string; same_merchant: boolean } | null;
  ground_truth: {
    status: "NONE" | "SMS_MATCHED" | "SMS_MISMATCH";
    sms_amount: number | null; sms_utr: string | null; bank: string | null;
    account_masked: string | null; amount_matched: boolean | null; utr_matched: boolean | null;
    message: string | null;
  };
  order: { order_ref: string; amount: number; status: "open" | "paid"; matched_by: "reference" | "amount" | "none" } | null;
  layer_scores: { forensics: number; rules: number; ground_truth: number; duplicate: number };
  strictness: string;
  handled: boolean; handled_at: string | null;
  created_at: string;                      // ISO 8601, UTC
  processing_time_seconds: number;
}

interface PublicVerification {
  id: string; verdict: Verdict; risk_score: number; amount: number | null;
  utr_masked: string; payment_app: string; checked_at: string; merchant_name: string;
  ground_truth_status: "NONE" | "SMS_MATCHED" | "SMS_MISMATCH";
}
```

### Dashboard
- `GET /api/dashboard/stats` → `{total_checks, confirmed_count, likely_genuine_count, suspicious_count, fake_count, reused_count, handled_count, rupees_saved, total_volume, trend: [{date: "YYYY-MM-DD", total, flagged}]}` (last 14 days)
- `GET /api/dashboard/history?search=&verdict=&app=&limit=20&offset=0` → `{total, limit, offset, items: [{id, verdict, risk_score, amount, utr, payment_app, is_reused, handled, created_at, image_available}]}`

`search` matches UTR or check ID. `verdict` is one of the four verdicts. `app` is a payment-app key.

### Order-bound QR
- `POST /api/qr/generate` `{amount, note?}` → `Order`
- `GET  /api/qr/orders?status=open|paid` → `{items: Order[]}`

`Order = {order_ref, amount, status: "open"|"paid", upi_uri, qr_image_data_url, merchant_upi_id, merchant_name, created_at, verification_id}`

### Demo samples (auth)
- `GET /api/demo/samples` → `{items: [{key, label, description, expected}]}`
- `GET /api/demo/samples/{key}` → image bytes, rendered fresh for the logged-in merchant (current time, their UPI ID)

### Public
- `GET /api/health` → `{status, version, ocr_engine, time}`
- `GET /api/rules` → contents of `rules.yaml`
- `GET /api/benchmark/results` → output of `scripts/evaluate_benchmark.py`, or `{status: "pending"}`

## Example: POS integration

```bash
curl -X POST "http://localhost:8000/api/verify/analyze" \
  -H "X-API-Key: $PRAMAAN_API_KEY" \
  -F "file=@screenshot.png"

curl -X POST "http://localhost:8000/api/verify/PRM-7KQ2M9XD/sms" \
  -H "X-API-Key: $PRAMAAN_API_KEY" -H "Content-Type: application/json" \
  -d '{"sms_text": "INR 750.00 credited to A/c XX4321 on 23-10-26 by UPI Ref 429182736451 - HDFC Bank"}'
```
