# Real payment screenshot handling fixes

## Root causes found

1. **BHIM status keyword missing in the original rules.** The original `backend/app/rules.yaml` allowed `success`, `completed`, and `successful`, but not `paid`. The screenshot shown in the report reads `Paid`, so the rule engine could flag a successful-looking BHIM receipt as “Payment is not marked successful.” The BHIM keywords now include `paid`.
2. **A genuine failed/pending screen could be called a fake image.** `R_STATUS_NOT_SUCCESS` used to be `CRITICAL`, and `compose_verdict()` treated almost every critical finding as proof of forgery. An unedited screenshot can truthfully show a failed or pending payment. The status finding is now high/medium severity and cannot, by itself, force `LIKELY FAKE`; it still keeps a merchant from accepting the payment.
3. **Repeated normal UI elements could trigger a copy-move warning.** App icons, checks, cards and repeating decorative patterns can produce ORB self-matches. The threshold has been raised from 16 to 28 matching votes and the warning penalty has been reduced from 5 to 3.
4. **Python 3.12 dependency setup.** ReportLab is pinned to 4.4.10 instead of the older 3.6.13, avoiding the reported `ft2build.h` source-build failure in a typical Python 3.12 setup.

## How to test

1. Start the project and use **Editing check only** to examine possible visual edits. It asks whether the image appears altered, not whether it paid a particular shop.
2. Use **Payment to my shop** only after the merchant's actual receiver UPI ID is configured.
3. Test BHIM samples with statuses `Paid`, `Success`, `Payment failed`, and `Pending`. `Paid` should not be treated as unsuccessful for BHIM; failed/pending receipts should be considered unsafe to accept, but should not be called forged from status alone.
4. Check the reference number/amount in recipient-controlled bank or merchant transaction history. A screenshot by itself cannot prove that funds reached the recipient.

## Validation status

The focused direct checks passed for BHIM `Paid` status and for a failed status returning `SUSPICIOUS` rather than `LIKELY FAKE`. Python syntax compilation passed for modified files. The full Pytest suite could not start in this environment because `bcrypt` is missing; it should be run after installing the project's full requirements.
