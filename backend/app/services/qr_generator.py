import base64
import io
import secrets
from urllib.parse import quote, urlencode

import qrcode


def new_order_ref() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I: easier to read off a phone
    return "ORD-" + "".join(secrets.choice(alphabet) for _ in range(6))


def upi_uri(merchant_upi_id: str, merchant_name: str, amount: float, order_ref: str) -> str:
    """NPCI UPI deep link. The order reference goes in `tn` (note) and `tr` (transaction ref)."""
    params = {"pa": merchant_upi_id, "pn": merchant_name, "am": f"{amount:.2f}", "cu": "INR",
              "tn": order_ref, "tr": order_ref}
    return "upi://pay?" + urlencode(params, quote_via=quote)


def qr_data_url(data: str) -> str:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=3)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0E1A2B", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
