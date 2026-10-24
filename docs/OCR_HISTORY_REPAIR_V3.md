# Pramaan OCR & transaction-history repair (v3)

## What changed

- Broader date parsing for receipts like `23rd Oct 26, 03:08 pm`, including ordinal days and two-digit years.
- Receiver extraction handles `Banking Name`, `Account Holder`, `Beneficiary Name`, `Paid To`, and same-line receiver names.
- OCR runs on the full screenshot, a contrast-enhanced pass, overlapping tall-screen crops, and an enhanced lower crop so small receiver/reference/date text is less likely to be lost when downscaled.
- BHIM's promotional `Paid in 1.86 Seconds` badge is not treated as the primary payment status, preventing a false layout warning when the real `Paid` status is above the amount.
- App identification includes FamPay/FamApp and common UPI provider labels where they are present in OCR-readable text.
- Payment-history list screens are detected separately from individual transaction details; fields from different history rows are not mixed into a pretend single receipt.
- The startup script chooses an available Python 3.12/3.11 before falling back, and the ReportLab dependency supports Python 3.12.

## Public sources and data policy

Official provider help pages explain that a user should select one history entry to see its detailed transaction page. See:

- Paytm receipt details: https://paytm.com/support/upi/how-to-get-upi-transaction-receipt-on-paytm
- Paytm transaction history: https://paytm.com/faqs/upi/how-to-check-upi-transaction-history-in-paytm
- Google Pay transaction history: https://support.google.com/pay/india/answer/7430307?hl=en-IN
- Google Pay status and bank-statement guidance: https://support.google.com/pay/india/answer/16920039?hl=en-IN and https://support.google.com/pay/india/answer/16919844?hl=en
- PhonePe UPI terms / History: https://www.phonepe.com/terms-conditions/upi/
- FamApp official site (formerly FamPay): https://www.famapp.in/
- BHIM UPI guidelines: https://www.bhimupi.org.in/files/bhim/BHIM-UPI-Guidelines.pdf

These are flow/layout/status references, not verified screenshot-authenticity labels. Public web images can be mockups, composites, altered images, or private transaction screenshots with unverified payment settlement. They are not automatically added to a training set or bundled into Pramaan. User-shared FamApp and Paytm examples are represented only by OCR-format regression cases; their image bytes and transaction truth are not included in this archive.

**No machine-learning model was trained in this release.** This release improves OCR, field extraction, screen-type detection and rule behavior. A properly labeled model would require a permissioned dataset with verified labels, separated into train/validation/test splits, and evaluation on unseen provider versions. A screenshot alone cannot prove that money reached the shop; use the merchant's bank credit / transaction history or verified transaction API as the final evidence.

## Retesting on macOS

1. Extract this archive to a fresh folder (do not extract over an old project).
2. In VS Code, open the newly extracted `Pramaan-main` folder.
3. In its integrated terminal run `chmod +x start.sh` and `./start.sh`.
4. Open `http://localhost:3000` and test both (a) one individual transaction-detail screen and (b) a multi-row history screen. The latter should say that a single transaction needs to be opened rather than claiming it is a fake receipt.

## Validation status

Focused regression checks cover date parsing, `Banking Name` extraction, BHIM `Paid` detection, timing badges, provider detection, and history-list separation. The full integration suite and a full frontend production build may still require dependencies that are not available in this packaging environment. Real settlement verification has not been performed.

## Reference screenshot sources found during research

A public FamPay-style transaction-detail sample appears in a user post at https://x.com/DepSuraj/status/1377200948259393542, and another at https://x.com/rajatrana6350/status/1621086800319238144. These may contain personal transaction details and a post may describe a payment problem, so this project does not download, redistribute, or label them as proven real payments. They informed only the text-layout regression pattern (FamCoins, Paid to, date/time, UPI transaction ID).

A full sweep of “every UPI app” is not realistically available as one trusted dataset. Official instructions exist for multiple apps, but sample UI images and news/blog images do not prove that the underlying payment settled. The official Paytm and Google Pay help pages advise selecting an individual history row to view its full transaction details; history-list screenshots should therefore be treated separately from individual receipts.
