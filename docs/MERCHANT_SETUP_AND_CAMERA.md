# Merchant setup and camera scanning

## Local startup

On macOS, `./start.sh` automatically prefers Python 3.12 or 3.11. If Python is installed at a non-standard path, set it explicitly, for example:

```bash
PYTHON=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 ./start.sh
```

The first launch needs internet access to install backend and frontend dependencies.

## Merchant profile

New account setup asks for three separate payment identity values:

- **Shop name**: the shop's display name.
- **Receiver/account name**: the beneficiary name that customers see when paying the UPI ID. It can be a proprietor's legal name and may differ from the shop name.
- **Registered UPI ID**: the exact VPA that should receive the payment.

The UPI ID is the strongest merchant match. If OCR cannot read it but a receiver name matches, Pramaan still warns that the UPI ID was not visible. Existing databases are migrated at startup and existing demo profiles get their receiver name set to the shop name. Existing users can correct the receiver name on Settings.

## Camera scan

The Verify page provides a live camera modal. It requests browser camera permission, previews a frame, captures a JPEG and sends it through the same analysis path as an uploaded image. Camera access works on `localhost` and secure HTTPS pages in browsers that support `getUserMedia`. Permission denial or unsupported browsers can fall back to the device camera picker or ordinary file upload. A photo of a screen can suffer glare/moire; the original screenshot file is preferable when available.

## Verdict semantics

- A receiver mismatch means the payment is not shown as going to this merchant; it does not prove that the image was forged.
- A failed or pending status means the proof is unsafe to accept; it is not, by itself, proof that the screenshot was manipulated.
- An old timestamp raises a replay-risk warning under the merchant's configured time window. It does not by itself prove forgery.
- Repeated visual patterns are weak forensic clues and cannot independently cause a fake verdict.
- Only a matching bank credit SMS/statement (amount plus transaction reference) can confirm that money reached the merchant. A screenshot alone never confirms settlement.

## OCR changes

The OCR pipeline now reads at higher resolution and merges a contrast-enhanced second pass. Status recognition uses whole-word matching and handles `Paid`, `Sent`, `Received`, `Successful`, and common failure/pending terms without accepting `Unsuccessful` as success.
