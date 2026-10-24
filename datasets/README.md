# Pramaan image-data collection

The repository currently uses OCR, deterministic payment rules and image-forensics heuristics. It does **not** contain a trained fake-vs-genuine screenshot classifier. The public source list in `public_reference_sources.csv` is a research index, not a ready-to-train binary dataset.

## Labels must reflect evidence, not appearance

- `confirmed_genuine`: only when the sample owner has permission to share it and a matching transaction is independently confirmed in the recipient's bank/merchant history or another reliable payment record.
- `confirmed_forgery`: only when the image is generated/edited in a controlled way with the edit known, or a specific image is directly and credibly documented as fabricated.
- `failed_or_pending_genuine`: an unedited screenshot can still show a failed or pending transfer. It is not a forged image, but it is not acceptable proof of a completed payment.
- `official_ui_mockup`, `reported_scam_composite`, `request_money_ui`, `unknown`: reference/negative-control labels; exclude them from the binary genuine-vs-forged training split.

News stories often use representational images, cropped composites, or illustrative mockups. A blog that discusses a scam does not automatically make each picture on the page a confirmed fake screenshot. The source registry deliberately flags examples that must not be used as binary labels.

## Add private examples safely

Put consented samples in `inbox/real/` or `inbox/fake/` only after removing names, UPI IDs, account numbers, phone numbers, transaction IDs, QR codes, and unrelated notifications. Preserve a separate secure ground-truth note showing how the label was confirmed; do not put sensitive ground-truth documents in this repository. Do not crop away app/status context just to create an easy label.

Use at least several hundred varied examples for an initial benchmark, then hundreds or thousands per class before trusting a learned image classifier. Split by source/person/device/app version before augmentation to avoid near-duplicate leakage. Hold out whole devices and app versions for testing. Augmentations of one screenshot are not independent samples.

## Important limitation

Pixels alone cannot establish that money reached the merchant. A realistic fake UI may be pixel-perfect; a genuine screenshot may be compressed, edited for privacy, or display a failed/pending state. The production decision must remain bank/merchant-ledger confirmation, not a model's binary claim.
