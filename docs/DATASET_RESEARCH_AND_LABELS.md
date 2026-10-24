# Public-source research notes for screenshot data

The reviewed sources and recommended use are listed in `datasets/public_reference_sources.csv`.

## Useful sources found

- PhonePe's safety blog discusses fake payment screenshot scams and recommends checking the actual payment state rather than trusting an image. https://www.phonepe.com/blog/trust-and-safety/heres-a-quick-guide-to-help-you-avoid-becoming-a-victim-of-fake-payment-screenshots-2/
- Hindustan Times reports a UPI scam attempt and embeds a composite containing a transaction-looking screen and chat context. Since it's a composite and is not a raw isolated receipt, do not train a binary image label without manual verification and permission. https://www.hindustantimes.com/trending/bengaluru-man-narrowly-escapes-upi-scam-trying-to-sell-ipad-here-s-how-he-foiled-it-101710998125314.html
- New Indian Express reports fabricated PhonePe screenshots made through a dummy app, but its displayed article photo is representational. The report helps identify the scam type; the article photo is not a fake receipt sample. https://www.newindianexpress.com/amp/story/states/odisha/2026/Sep/12/fake-phonepe-payment-screenshots-two-arrested
- NPCI's UPI HELP guidelines contain an official success-flow mockup (PDF page 20). It can inform status vocabulary and UI structure, but must not be labeled a real transaction. https://www.npci.org.in/uploads/UPI_Help_Brand_Guidelines_86c8c28922.pdf
- Google Pay Help explains transaction-history and status checks: https://support.google.com/pay/india/answer/7430307?hl=en-IN and https://support.google.com/pay/india/answer/16920039?hl=en-IN
- Paytm and Moneycontrol explain why the recipient should confirm in their own transaction history/account: https://paytm.com/blog/payments/upi/upi-frauds/ and https://www.moneycontrol.com/news/business/personal-finance/don-t-trust-the-screenshot-how-to-spot-a-fake-upi-payment-13996275.html

## Why a binary model has not been trained yet

Public pages do not provide a balanced, ground-truth dataset of both genuine and forged receipts. Some pages use mockups, representational photos, composites or images whose transaction status cannot be independently verified. Treating all screenshots on a scam blog as `fake` and all official-looking screens as `real` would introduce mislabeled data. The current project uses OCR, deterministic payment rules and image-forensics heuristics; it does not yet contain a trained image classifier.

The next useful step is a consented, privacy-redacted set of screenshots paired with independently verified labels. For genuine samples, confirm the payment in the recipient's bank/merchant transaction history. For fake samples, use controlled edits with known change locations or an individual example explicitly confirmed as fabricated. Label failed/pending genuine screens separately rather than calling them fake images.


## Current work: FamPay/FamApp and Paytm history examples

The recent user-provided FamPay/FamApp and Paytm images are being used to inform **OCR regression formats**, not as automatic binary training labels. Paytm's official receipt guide says the detailed transaction view contains the receiver/payee UPI ID, UPI reference and payment time; its History list is a separate screen, and tapping a row opens detail. Google Pay describes the same list-to-detail interaction. Sources:

- Paytm receipt detail: https://paytm.com/support/upi/how-to-get-upi-transaction-receipt-on-paytm
- Paytm transaction history: https://paytm.com/faqs/upi/how-to-check-upi-transaction-history-in-paytm
- Google Pay history/detail workflow: https://support.google.com/pay/india/answer/7430307?hl=en-IN
- Google Pay status meanings: https://support.google.com/pay/india/answer/16920039?hl=en-IN
- PhonePe History and issuer records: https://www.phonepe.com/terms-conditions/upi/

The user's screenshots are not included in the downloadable source archive. Payment screenshots may contain personal transaction data, so only anonymized text-pattern tests are committed. Public webpage images are not copied into the source tree because a public URL is not the same as a license to redistribute or a verified `real`/`fake` label. They are retained as source links for manual review only.

## How to make the next OCR benchmark stronger

For genuine samples, first validate the amount + UPI reference against the merchant's own bank/settlement history and redact unrelated data. For fabricated samples, record the known edit and the changed area; don't label an authentic failed/pending screen as a fake image. Keep history-list pages in a separate `history_list` class instead of mixing them with one-transaction `transaction_detail` screenshots.
