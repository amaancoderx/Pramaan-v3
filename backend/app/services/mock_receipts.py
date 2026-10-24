"""Generic, brand-free mock UPI receipts and scripted tamper operations.

Used by scripts/generate_dataset.py (benchmark set), the demo-sample endpoint, demo seeding and tests.
Every receipt carries a visible "MOCK RECEIPT" footer. No real app logos, names or colours are used.
"""
import io
import random
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from PIL.PngImagePlugin import PngInfo

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FONT_REGULAR = FONT_DIR / "DejaVuSans.ttf"
FONT_BOLD = FONT_DIR / "DejaVuSans-Bold.ttf"
FONT_MONO = FONT_DIR / "DejaVuSansMono.ttf"

# Neutral themes (header colour, accent) that do not imitate any real payment app.
THEMES = {
    "slate": ((38, 50, 72), (30, 158, 90)),
    "teal": ((14, 116, 120), (30, 158, 90)),
    "indigo": ((52, 58, 120), (30, 158, 90)),
    "graphite": ((48, 48, 52), (30, 158, 90)),
}

BG = (250, 250, 248)
CARD = (255, 255, 255)
INK = (24, 28, 36)
MUTED = (110, 116, 128)
LINE = (226, 228, 232)

Box = Tuple[int, int, int, int]  # x0, y0, x1, y1


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve",
         "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _two(n: int) -> str:
    return _ONES[n] if n < 20 else (_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else ""))


def _three(n: int) -> str:
    parts = []
    if n >= 100:
        parts.append(f"{_ONES[n // 100]} Hundred")
    if n % 100:
        parts.append(_two(n % 100))
    return " ".join(parts)


def amount_to_words(amount: float) -> str:
    """Indian numbering: 125000 -> 'Rupees One Lakh Twenty Five Thousand Only'."""
    n = int(round(amount))
    if n == 0:
        return "Rupees Zero Only"
    parts = []
    for unit, size in (("Crore", 10_000_000), ("Lakh", 100_000), ("Thousand", 1000)):
        if n >= size:
            parts.append(f"{_three(n // size)} {unit}")
            n %= size
    if n:
        parts.append(_three(n))
    return "Rupees " + " ".join(parts) + " Only"


def format_inr(amount: float, decimals: bool = False) -> str:
    whole = int(amount)
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    if decimals:
        s += f".{int(round((amount - whole) * 100)):02d}"
    return s


def format_txn_time(dt: datetime) -> str:
    return dt.strftime("%d %b %Y, %I:%M %p").lstrip("0")


def random_utr(rng: random.Random) -> str:
    while True:
        utr = str(rng.randint(2, 6)) + "".join(str(rng.randint(0, 9)) for _ in range(11))
        if len(set(utr)) > 4:
            return utr


@dataclass
class ReceiptSpec:
    amount: float
    utr: str
    txn_time: datetime
    receiver_name: str
    receiver_upi: str
    sender_name: str = "Rahul Verma"
    sender_upi: str = "rahulv@okaxis"
    screenshot_delay_min: int = 2
    note: Optional[str] = None
    theme: str = "slate"
    width: int = 1080
    height: int = 2340
    status_text: str = "Payment successful"
    words_amount: Optional[float] = None  # amount shown in words (defaults to amount)


@dataclass
class Rendered:
    image: Image.Image
    spec: ReceiptSpec
    boxes: Dict[str, Box] = field(default_factory=dict)  # field -> text box in pixels


class _Canvas:
    def __init__(self, spec: ReceiptSpec):
        self.spec = spec
        self.s = spec.width / 1080.0
        self.img = Image.new("RGB", (spec.width, spec.height), BG)
        self.d = ImageDraw.Draw(self.img)
        self.boxes: Dict[str, Box] = {}

    def px(self, v: float) -> int:
        return int(round(v * self.s))

    def text(self, key: Optional[str], xy: Tuple[float, float], txt: str, font_path: Path, size: float,
             fill=INK, anchor: str = "la") -> Box:
        f = _font(font_path, self.px(size))
        pos = (self.px(xy[0]), self.px(xy[1]))
        self.d.text(pos, txt, font=f, fill=fill, anchor=anchor)
        box = tuple(int(v) for v in self.d.textbbox(pos, txt, font=f, anchor=anchor))
        self.boxes[key or f"_text{len(self.boxes)}"] = box  # type: ignore[assignment]
        return box  # type: ignore[return-value]


def render_receipt(spec: ReceiptSpec) -> Rendered:
    c = _Canvas(spec)
    d, px = c.d, c.px
    header, accent = THEMES.get(spec.theme, THEMES["slate"])
    w = spec.width

    # Status bar: the phone clock, captured a few minutes after the payment.
    shot_time = spec.txn_time + timedelta(minutes=spec.screenshot_delay_min)
    c.text("status_bar_time", (48, 22), shot_time.strftime("%H:%M"), FONT_BOLD, 32)
    c.text(None, (1032, 22), "4G  86%", FONT_REGULAR, 28, anchor="ra")

    d.rectangle([0, px(80), w, px(250)], fill=header)
    c.text(None, (60, 140), "Payment receipt", FONT_BOLD, 44, fill=(255, 255, 255))
    c.text(None, (1020, 150), "UPI", FONT_BOLD, 30, fill=(220, 228, 236), anchor="ra")

    # Success mark
    cx, cy, r = w // 2, px(410), px(78)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=accent)
    d.line([(cx - px(34), cy + px(2)), (cx - px(8), cy + px(28)), (cx + px(38), cy - px(26))],
           fill=(255, 255, 255), width=px(14), joint="curve")

    c.text("status", (540, 540), spec.status_text, FONT_BOLD, 44, anchor="ma")
    c.text("amount", (540, 630), "₹" + format_inr(spec.amount), FONT_BOLD, 104, anchor="ma")
    words = amount_to_words(spec.words_amount if spec.words_amount is not None else spec.amount)
    c.text("amount_in_words", (540, 790), words, FONT_REGULAR, 30, fill=MUTED, anchor="ma")

    top = 880
    d.rounded_rectangle([px(36), px(top), w - px(36), px(top + 1150 if spec.note else top + 1000)],
                        radius=px(28), fill=CARD, outline=LINE, width=max(1, px(2)))

    rows = [
        ("Paid to", [("receiver", spec.receiver_name, FONT_BOLD, 40),
                     ("receiver_upi_id", spec.receiver_upi, FONT_REGULAR, 34)]),
        ("From", [("sender", spec.sender_name, FONT_BOLD, 40),
                  ("sender_upi", spec.sender_upi, FONT_REGULAR, 34)]),
        ("UPI Ref No.", [("utr", spec.utr, FONT_BOLD, 40)]),
        ("Date & time", [("timestamp", format_txn_time(spec.txn_time), FONT_BOLD, 40)]),
    ]
    if spec.note:
        rows.append(("Note", [("note", spec.note, FONT_BOLD, 40)]))

    y = top + 50
    for i, (label, values) in enumerate(rows):
        c.text(f"label_{i}", (80, y), label, FONT_REGULAR, 30, fill=MUTED)
        y += 48
        for key, val, fp, size in values:
            c.text(key, (80, y), val, fp, size)
            y += 58 if size >= 40 else 52
        y += 40
        if i < len(rows) - 1:
            d.line([px(80), px(y - 22), w - px(80), px(y - 22)], fill=LINE, width=max(1, px(2)))

    c.text(None, (540, (spec.height / c.s) - 120), "MOCK RECEIPT  ·  Pramaan synthetic test data",
           FONT_REGULAR, 26, fill=(150, 154, 162), anchor="ma")
    return Rendered(image=c.img, spec=spec, boxes=c.boxes)


# --------------------------------------------------------------------------------------------
# Tamper operations. Each mimics a real editing habit and leaves the artefacts a real edit would.
# --------------------------------------------------------------------------------------------

def _pad(box: Box, p: int, img: Image.Image) -> Box:
    return (max(0, box[0] - p), max(0, box[1] - p), min(img.width, box[2] + p), min(img.height, box[3] + p))


def _overwrite(r: Rendered, key: str, new_text: str, rng: random.Random, *, font: Path = FONT_BOLD,
               size_scale: float = 1.0, dx: int = 0, dy: int = 0, patch_delta: int = 3, noise: float = 0.0,
               ink=(52, 56, 64), blur: float = 0.0) -> None:
    """Paint over a field with an approximate background patch and type new text, like a phone photo editor."""
    img = r.image
    box = r.boxes[key]
    x0, y0, x1, y1 = _pad(box, 10, img)
    # Patch wide enough for the new text too.
    # Pick a font size whose ink height matches the original text, then apply the deliberate scale error.
    probe = ImageFont.truetype(str(font), 100).getbbox(new_text)
    base_size = 100 * (box[3] - box[1]) / max(1, probe[3] - probe[1])
    f = ImageFont.truetype(str(font), max(8, int(base_size * size_scale)))
    ink_box = f.getbbox(new_text)  # ink extents relative to the drawing origin
    tw, th = ink_box[2] - ink_box[0], ink_box[3] - ink_box[1]
    centered = key in ("amount", "status", "amount_in_words")
    if centered:
        cx = (box[0] + box[2]) // 2
        x0 = min(x0, int(cx - tw / 2) - 12)
        x1 = max(x1, int(cx + tw / 2) + 12)
    else:
        x1 = max(x1, int(box[0] + tw) + 14)
    y1 = min(img.height, max(y1, box[1] + dy + th + 10))

    sample = img.getpixel((max(0, x0 - 4), max(0, y0 - 4)))
    patch_col = tuple(max(0, min(255, ch - patch_delta)) for ch in sample)
    patch = Image.new("RGB", (x1 - x0, y1 - y0), patch_col)
    if noise > 0:
        import numpy as np
        arr = np.asarray(patch).astype(np.float32)
        arr += np.random.default_rng(rng.randint(0, 10_000)).normal(0, noise, arr.shape)
        patch = Image.fromarray(arr.clip(0, 255).astype("uint8"))
    pd = ImageDraw.Draw(patch)
    # Align the new ink box with the old one (top edge), as a person nudging text in an editor would.
    ty = (box[1] - y0) + dy - ink_box[1]
    if centered:
        pd.text(((x1 - x0 - tw) / 2 + dx - ink_box[0], ty), new_text, font=f, fill=ink)
    else:
        pd.text((box[0] - x0 + dx - ink_box[0], ty), new_text, font=f, fill=ink)
    if blur:
        patch = patch.filter(ImageFilter.GaussianBlur(blur))
    img.paste(patch, (x0, y0))
    r.boxes[key] = (x0, y0, x1, y1)


def _clone(r: Rendered, src: Box, dst_xy: Tuple[int, int]) -> None:
    region = r.image.crop(src)
    r.image.paste(region, dst_xy)


@dataclass
class Sample:
    sample_id: str
    label: str              # "clean" | "tampered"
    tamper_type: str        # "none" or a tamper category
    description: str
    image_bytes: bytes
    ext: str                # ".png" | ".jpg"
    spec: ReceiptSpec


def encode(img: Image.Image, fmt: str = "PNG", quality: int = 92, software: Optional[str] = None) -> Tuple[bytes, str]:
    buf = io.BytesIO()
    if fmt == "PNG":
        info = PngInfo()
        if software:
            info.add_text("Software", software)
        img.save(buf, format="PNG", pnginfo=info, optimize=True)
        return buf.getvalue(), ".png"
    exif = None
    if software:
        ex = Image.Exif()
        ex[0x0131] = software  # Software tag
        exif = ex.tobytes()
    img.save(buf, format="JPEG", quality=quality, **({"exif": exif} if exif else {}))
    return buf.getvalue(), ".jpg"


FIRST_NAMES = ["Rahul", "Priya", "Amit", "Sneha", "Vikram", "Anjali", "Rohan", "Kavya", "Arjun", "Meera",
               "Suresh", "Pooja", "Manish", "Divya", "Karan", "Neha", "Imran", "Fatima", "Gurpreet", "Lakshmi"]
LAST_NAMES = ["Verma", "Sharma", "Patel", "Reddy", "Iyer", "Khan", "Singh", "Das", "Nair", "Joshi", "Gupta", "Mehta"]
BANK_HANDLES = ["okaxis", "oksbi", "okicici", "ybl", "ibl", "paytm", "upi", "axl"]
AMOUNTS = [120, 150, 249, 380, 450, 500, 620, 750, 899, 1250, 1499, 1800, 2200, 2750, 3500, 4999, 6400, 8200,
           12500, 18750, 24000]
SIZES = [(1080, 2340), (1080, 2400), (720, 1600), (1080, 1920), (1440, 3120)]


def random_spec(rng: random.Random, now: datetime, merchant_name: str, merchant_upi: str) -> ReceiptSpec:
    first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
    w, h = rng.choice(SIZES)
    delay = rng.randint(0, 12)
    txn_time = now - timedelta(minutes=delay + rng.randint(1, 30))
    return ReceiptSpec(
        amount=float(rng.choice(AMOUNTS)),
        utr=random_utr(rng),
        txn_time=txn_time.replace(second=0, microsecond=0),
        screenshot_delay_min=delay,
        receiver_name=merchant_name,
        receiver_upi=merchant_upi,
        sender_name=f"{first} {last}",
        sender_upi=f"{first.lower()}{rng.randint(10, 99)}@{rng.choice(BANK_HANDLES)}",
        note=rng.choice([None, None, "Groceries", "Bill payment", None]),
        theme=rng.choice(list(THEMES)),
        width=w,
        height=h,
    )


# Each tamper builder returns (description, bytes, ext). They receive a freshly rendered clean receipt.
TamperFn = Callable[[Rendered, random.Random, datetime], Tuple[str, bytes, str]]


def t_edited_amount(r: Rendered, rng: random.Random, now: datetime):
    new_amt = r.spec.amount * rng.choice([10, 4, 2.5]) if r.spec.amount < 5000 else r.spec.amount + 9000
    _overwrite(r, "amount", "₹" + format_inr(new_amt), rng, size_scale=rng.choice([0.94, 1.0, 1.06]),
               patch_delta=rng.choice([2, 4, 6]), ink=(36, 40, 48))
    return (f"Amount edited from {format_inr(r.spec.amount)} to {format_inr(new_amt)}; words left unchanged",
            *encode(r.image))


def t_edited_utr(r: Rendered, rng: random.Random, now: datetime):
    variant = rng.choice(["short", "repeat", "pasted"])
    if variant == "short":
        new = r.spec.utr[:11]
        desc = "UTR edited to 11 digits"
    elif variant == "repeat":
        new = rng.choice("13579") * 12 if rng.random() < 0.5 else "123456789012"
        desc = f"UTR replaced with dummy sequence {new}"
    else:
        new = random_utr(rng)
        desc = "UTR replaced with a plausible number typed in a slightly different font"
    _overwrite(r, "utr", new, rng, font=FONT_REGULAR if variant == "pasted" else FONT_BOLD,
               size_scale=0.88 if variant == "pasted" else 1.0, dx=rng.choice([6, 10]), patch_delta=4,
               ink=(70, 74, 82))
    return desc, *encode(r.image)


def t_edited_date(r: Rendered, rng: random.Random, now: datetime):
    variant = rng.choice(["future", "old", "clock"])
    if variant == "future":
        new_dt = r.spec.txn_time + timedelta(days=2)
        desc = "Date edited to two days in the future"
    elif variant == "old":
        new_dt = r.spec.txn_time - timedelta(days=3)
        desc = "Old receipt with date edited; transaction is days outside the allowed window"
    else:
        new_dt = r.spec.txn_time + timedelta(minutes=55)
        desc = "Time edited to after the phone clock in the status bar"
    _overwrite(r, "timestamp", format_txn_time(new_dt), rng, patch_delta=3, dy=2, ink=(40, 44, 52))
    return desc, *encode(r.image)


def t_cloned_digits(r: Rendered, rng: random.Random, now: datetime):
    """Copy-move inside the image: duplicate the leading digit block of the amount over the following digits."""
    x0, y0, x1, y1 = r.boxes["amount"]
    glyph_w = (x1 - x0) / max(1, len("₹" + format_inr(r.spec.amount)))
    src = (int(x0 + glyph_w * 1.0), y0 - 4, int(x0 + glyph_w * 2.05), y1 + 4)
    _clone(r, src, (int(x0 + glyph_w * 2.05), y0 - 4))
    # Also clone a whole detail value elsewhere on the card: a second, larger copied block.
    ux0, uy0, ux1, uy1 = r.boxes["utr"]
    _clone(r, (ux0, uy0 - 2, ux0 + (ux1 - ux0) // 2, uy1 + 2), (ux0 + (ux1 - ux0) // 2, uy0 - 2))
    return "Digits duplicated by copy-move in the amount and UTR", *encode(r.image)


def t_pasted_receiver(r: Rendered, rng: random.Random, now: datetime):
    fake_handle = rng.choice(["quickpay.store@ybl", "sharma.kirana1@okaxis", "kiranastore@ibl", "rk.traders@upi"])
    _overwrite(r, "receiver_upi_id", fake_handle, rng, font=FONT_REGULAR, patch_delta=3, ink=(30, 34, 42))
    return f"Receiver UPI ID pasted over with {fake_handle}", *encode(r.image)


def t_heavy_compression(r: Rendered, rng: random.Random, now: datetime):
    """A careful edit (amount and words both changed) hidden under heavy JPEG re-compression."""
    new_amt = r.spec.amount * 3
    _overwrite(r, "amount", "₹" + format_inr(new_amt), rng, patch_delta=1, ink=INK)
    _overwrite(r, "amount_in_words", amount_to_words(new_amt), rng, font=FONT_REGULAR, patch_delta=1, ink=MUTED)
    img = r.image.resize((int(r.image.width * 0.75), int(r.image.height * 0.75)), Image.BILINEAR)
    q = rng.choice([18, 24, 30])
    return f"Amount and words edited consistently, then re-saved as JPEG quality {q}", *encode(img, "JPEG", q)


def t_editor_software(r: Rendered, rng: random.Random, now: datetime):
    sw = rng.choice(["Adobe Photoshop 25.4 (Windows)", "PicsArt Photo Studio", "Snapseed 2.21"])
    new_amt = r.spec.amount + 1000
    _overwrite(r, "amount", "₹" + format_inr(new_amt), rng, patch_delta=0, ink=INK)
    _overwrite(r, "amount_in_words", amount_to_words(new_amt), rng, font=FONT_REGULAR, patch_delta=0, ink=MUTED)
    fmt = rng.choice(["PNG", "JPEG"])
    return f"Edited in a photo editor; file metadata says '{sw}'", *encode(r.image, fmt, 90, software=sw)


TAMPERS: Dict[str, TamperFn] = {
    "edited_amount": t_edited_amount,
    "edited_utr": t_edited_utr,
    "edited_date": t_edited_date,
    "cloned_digits": t_cloned_digits,
    "pasted_receiver": t_pasted_receiver,
    "heavy_compression": t_heavy_compression,
    "editor_software": t_editor_software,
}

# 20 tampered samples across seven scripted categories.
TAMPER_PLAN = [("edited_amount", 3), ("edited_utr", 3), ("edited_date", 3), ("cloned_digits", 3),
               ("pasted_receiver", 3), ("heavy_compression", 3), ("editor_software", 2)]


def build_dataset(now: datetime, merchant_name: str, merchant_upi: str, seed: int = 2026,
                  n_clean: int = 20) -> List[Sample]:
    rng = random.Random(seed)
    samples: List[Sample] = []
    for i in range(n_clean):
        spec = random_spec(rng, now, merchant_name, merchant_upi)
        r = render_receipt(spec)
        fmt = "JPEG" if i % 4 == 3 else "PNG"  # a share of genuine screenshots arrive as JPEG
        data, ext = encode(r.image, fmt, 92)
        samples.append(Sample(f"CLEAN-{i + 1:02d}", "clean", "none", "Unedited mock receipt", data, ext, spec))

    n = 0
    for kind, count in TAMPER_PLAN:
        for _ in range(count):
            n += 1
            spec = random_spec(rng, now, merchant_name, merchant_upi)
            r = render_receipt(spec)
            desc, data, ext = TAMPERS[kind](r, rng, now)
            samples.append(Sample(f"TAMPER-{n:02d}", "tampered", kind, desc, data, ext, spec))
    return samples


DEMO_SAMPLES = {
    "clean": ("Unedited receipt", "A mock receipt paid to your UPI ID a few minutes ago.", "LIKELY GENUINE"),
    "edited_amount": ("Edited amount", "Amount changed in an editor; amount in words left as it was.", "LIKELY FAKE"),
    "wrong_receiver": ("Wrong receiver", "Payment went to a different UPI ID.", "LIKELY FAKE"),
    "dummy_utr": ("Dummy UTR", "Reference number is a fake repeating sequence.", "LIKELY FAKE"),
    "edited_date": ("Old receipt, new date", "An old payment with its date edited.", "SUSPICIOUS"),
    "photo_editor": ("Photo-editor file", "Metadata shows the image went through an editor.", "LIKELY FAKE"),
    "reused": ("Same receipt again", "Your last 'Unedited receipt', cropped and re-compressed.", "LIKELY FAKE"),
}


def render_demo(key: str, now: datetime, merchant_name: str, merchant_upi: str,
                rng: Optional[random.Random] = None) -> Tuple[bytes, str]:
    rng = rng or random.Random()
    spec = random_spec(rng, now, merchant_name, merchant_upi)
    spec = replace(spec, width=1080, height=2340)
    r = render_receipt(spec)
    if key == "clean":
        return encode(r.image)
    if key == "edited_amount":
        _, data, ext = t_edited_amount(r, rng, now)
        return data, ext
    if key == "wrong_receiver":
        _, data, ext = t_pasted_receiver(r, rng, now)
        return data, ext
    if key == "dummy_utr":
        _overwrite(r, "utr", "111111111111", rng, patch_delta=3, ink=(60, 64, 72))
        return encode(r.image)
    if key == "edited_date":
        r = render_receipt(replace(spec, txn_time=spec.txn_time - timedelta(days=3)))
        return encode(r.image)
    if key == "photo_editor":
        _, data, ext = t_editor_software(r, random.Random(7), now)
        return data, ext
    raise KeyError(key)


def crop_and_recompress(data: bytes, quality: int = 70) -> Tuple[bytes, str]:
    """What a reused screenshot usually looks like after being forwarded: status bar cropped, re-compressed."""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = img.size
    img = img.crop((0, int(h * 0.035), w, int(h * 0.93)))
    return encode(img, "JPEG", quality)
