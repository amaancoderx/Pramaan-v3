"""Heuristic image forensics for real-world payment screenshots.

App versions, themes, resizing and compression vary. Pixel-based findings are therefore supporting signals,
not proof of payment or proof of fraud; the bank record remains the source of truth.
"""
import io
import logging
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import ExifTags, Image

from app.schemas.rules import BoundingBox, PassedCheck, ReasonDetail
from app.schemas.verification import ExtractedData

log = logging.getLogger("pramaan.forensics")

EDITOR_KEYWORDS = ["photoshop", "picsart", "canva", "pixlr", "snapseed", "gimp", "lightroom", "photo editor",
                   "paint.net", "vsco", "photoroom", "facetune", "polarr", "inshot", "meitu", "affinity", "fotor"]
CRITICAL_FIELDS = [("amount", "amount"), ("utr", "UTR"), ("timestamp", "date and time"),
                   ("receiver_upi_id", "receiver UPI ID")]
# Pixel/metadata cues are correlated and can occur in genuine app screenshots. Keep their weights
# conservative; none of these cues alone proves that a payment receipt was forged.
PENALTY = {"editor": 28, "copy_move": 2, "background": 15, "text_region": 12, "ela": 10,
           "recompression": 6, "dimensions": 6, "added_text": 18}
# Fields whose text is compared with the rest of the screenshot's text (text_history).
TRACE_FIELDS = [("amount", "amount"), ("amount_in_words", "amount in words"), ("utr", "UTR"),
                ("timestamp", "date and time"), ("receiver_upi_id", "receiver UPI ID"), ("receiver", "receiver name")]
TRACE_RATIO = 1.5  # a field must carry 1.5x the median trace of the other text to count as added later
MAX_FORENSIC_PENALTY = 45.0

# Standard JPEG luminance quantisation table (quality 50), used to estimate the saved quality.
_STD_LUMA = np.array([16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55, 14, 13, 16, 24, 40, 57, 69, 56,
                      14, 17, 22, 29, 51, 87, 80, 62, 18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113,
                      92, 49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99], dtype=np.float64)


def _reason(code, severity, title, message, penalty, evidence="heatmap", field=None, region=None, value=None):
    return ReasonDetail(code=code, severity=severity, layer="forensics", title=title, message=message, field=field,
                        penalty=float(penalty), evidence_type=evidence, evidence_value=value,
                        region=BoundingBox(**region) if isinstance(region, dict) else region)


def estimate_jpeg_quality(pil: Image.Image) -> Optional[int]:
    q = getattr(pil, "quantization", None)
    if not q or 0 not in q:
        return None
    table = np.array(q[0], dtype=np.float64)
    if table.size != 64:
        return None
    scale = float(np.mean(table / _STD_LUMA) * 100.0)
    quality = (200 - scale) / 2 if scale <= 100 else 5000 / scale
    return int(max(1, min(100, round(quality))))


class ForensicEngine:
    # ---------------------------------------------------------------- metadata & file
    def inspect_file(self, data: bytes) -> Dict[str, Any]:
        out: Dict[str, Any] = {"format": None, "software": None, "camera": None, "jpeg_quality": None,
                               "width": 0, "height": 0, "reasons": [], "passed": []}
        try:
            pil = Image.open(io.BytesIO(data))
        except Exception:
            return out
        out["format"] = pil.format
        out["width"], out["height"] = pil.size
        w, h = pil.size

        tags: List[str] = []
        for k, v in (pil.info or {}).items():
            if str(k).lower() in ("software", "creator", "tool", "comment", "description", "xmp", "xml:com.adobe.xmp"):
                tags.append(str(v))
        try:
            exif = pil.getexif()
            for tag_id, value in exif.items():
                name = ExifTags.TAGS.get(tag_id, str(tag_id))
                if name in ("Software", "ProcessingSoftware", "ImageDescription", "Artist", "HostComputer"):
                    tags.append(str(value))
                if name in ("Make", "Model"):
                    out["camera"] = f"{out['camera'] or ''} {value}".strip()
        except Exception:
            pass
        joined = " | ".join(tags)
        hit = next((kw for kw in EDITOR_KEYWORDS if kw in joined.lower()), None)
        if hit:
            out["software"] = joined[:120]
            out["reasons"].append(_reason(
                "F_EDITOR_SOFTWARE", "HIGH", "Photo-editor metadata found",
                f"The file's metadata names '{joined[:80]}'. This can mean the image was opened and saved in an editor, "
                "but metadata alone does not prove payment details were altered. Check the other findings and confirm "
                "the payment with the bank.", PENALTY["editor"], evidence="metadata", value={"software": joined[:200]}))
        else:
            out["passed"].append(PassedCheck(code="F_METADATA_CLEAN", layer="forensics",
                                             title="No photo-editor traces in file metadata"))

        ratio = max(w, h) / max(1, min(w, h))
        if ratio < 1.55 or ratio > 2.45:
            out["reasons"].append(_reason(
                "F_UNNATURAL_DIMENSIONS", "MEDIUM", "Unusual screenshot shape",
                f"{w}×{h} px (ratio {ratio:.2f}) is not a phone screen shape. It may be cropped or assembled.",
                PENALTY["dimensions"], evidence="metadata", value={"width": w, "height": h}))
        else:
            out["passed"].append(PassedCheck(code="F_DIMENSIONS", layer="forensics",
                                             title="Image has phone-screen proportions"))

        if pil.format == "JPEG":
            q = estimate_jpeg_quality(pil)
            out["jpeg_quality"] = q
            if q is not None and q < 50:
                out["reasons"].append(_reason(
                    "F_HEAVY_RECOMPRESSION", "MEDIUM", "Heavily re-compressed image",
                    f"Saved at about {q}% JPEG quality. Heavy compression hides editing traces, so pixel checks "
                    "are less reliable. Confirm with your bank SMS.", PENALTY["recompression"], evidence="metadata",
                    value={"jpeg_quality": q}))
        return out

    # ---------------------------------------------------------------- ELA
    @staticmethod
    def ela_map(img: np.ndarray, quality: int = 90) -> np.ndarray:
        ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
        resaved = cv2.imdecode(enc, cv2.IMREAD_COLOR)
        return cv2.cvtColor(cv2.absdiff(img, resaved), cv2.COLOR_BGR2GRAY).astype(np.float32)

    @staticmethod
    def flat_mask(gray: np.ndarray) -> np.ndarray:
        """Pixels in visually flat areas, away from text strokes and edges."""
        edges = cv2.Canny(gray, 40, 120)
        near_edge = cv2.dilate(edges, np.ones((7, 7), np.uint8)) > 0
        return ~near_edge

    def ela_anomalies(self, img: np.ndarray, gray: np.ndarray, ela: np.ndarray) -> List[Dict[str, int]]:
        flat = self.flat_mask(gray)
        vals = ela[flat]
        if vals.size < 1000:
            return []
        base = float(np.percentile(vals, 99))
        thresh = max(6.0, base * 3)
        hot = ((ela > thresh) & flat).astype(np.uint8)
        hot = cv2.morphologyEx(hot, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        n, _, stats, _ = cv2.connectedComponentsWithStats(hot)
        h, w = gray.shape
        min_area = max(250, int(w * h * 0.0002))
        regions = []
        for i in range(1, n):
            x, y, bw, bh, area = stats[i]
            if area >= min_area:
                regions.append({"x": int(x), "y": int(y), "width": int(bw), "height": int(bh)})
        return regions[:6]

    @staticmethod
    def render_heatmap(img: np.ndarray, ela: np.ndarray, regions: List[BoundingBox], out_path: str) -> None:
        norm = np.clip(ela * (255.0 / max(8.0, float(np.percentile(ela, 99.7)))), 0, 255).astype(np.uint8)
        norm = cv2.GaussianBlur(norm, (0, 0), 2)
        colored = cv2.applyColorMap(norm, cv2.COLORMAP_INFERNO)
        dim = (img * 0.45).astype(np.uint8)
        blended = cv2.addWeighted(dim, 1.0, colored, 0.85, 0)
        t = max(2, img.shape[1] // 300)
        for r in regions:
            cv2.rectangle(blended, (r.x - 6, r.y - 6), (r.x + r.width + 6, r.y + r.height + 6), (60, 60, 255), t)
        h, w = blended.shape[:2]
        if w > 900:
            blended = cv2.resize(blended, (900, int(h * 900 / w)), interpolation=cv2.INTER_AREA)
        cv2.imwrite(out_path, blended, [cv2.IMWRITE_JPEG_QUALITY, 85])

    # ---------------------------------------------------------------- copy-move
    @staticmethod
    def copy_move(gray: np.ndarray, lossless: bool, text_boxes: List[Dict[str, int]]
                  ) -> Tuple[int, Optional[Dict[str, int]], Optional[Dict[str, int]]]:
        """ORB keypoint self-matching with displacement voting, outside text.

        Inside text, a cloned digit is identical to a normally repeated digit (phones render each glyph the same
        way), so text is masked out and left to the cross-field rules. Outside text, many keypoints that all
        reappear at one displacement mean a copied patch (badges, ticks, painted areas). ORB survives the
        resizing and re-compression that break exact pixel matching."""
        h, w = gray.shape
        scale = min(1.0, 720 / w)
        small = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else gray
        mask = np.full(small.shape, 255, np.uint8)
        for b in text_boxes:
            x0, y0 = int((b["x"] - 6) * scale), int((b["y"] - 6) * scale)
            x1, y1 = int((b["x"] + b["width"] + 6) * scale), int((b["y"] + b["height"] + 6) * scale)
            cv2.rectangle(mask, (x0, y0), (x1, y1), 0, -1)
        orb = cv2.ORB_create(nfeatures=1500, scaleFactor=1.2, nlevels=4, edgeThreshold=15, patchSize=15)
        kps, des = orb.detectAndCompute(small, mask)
        if des is None or len(kps) < 10:
            return 0, None, None
        matches = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(des, des, k=3)
        votes: Counter = Counter()
        pairs: Dict[Tuple[int, int], List[Tuple[Tuple[float, float], Tuple[float, float]]]] = {}
        for ms in matches:
            for m in ms[1:]:  # ms[0] is the keypoint itself
                if m.distance > 40:
                    continue
                p1, p2 = kps[m.queryIdx].pt, kps[m.trainIdx].pt
                if p1 > p2:
                    p1, p2 = p2, p1
                dx, dy = p2[0] - p1[0], p2[1] - p1[1]
                if abs(dx) + abs(dy) < 20:
                    continue
                key = (int(round(dx / 6)), int(round(dy / 6)))
                votes[key] += 1
                pairs.setdefault(key, []).append((p1, p2))
        if not votes:
            return 0, None, None
        key, n = votes.most_common(1)[0]
        pts = pairs[key]
        inv = 1 / scale

        def box(points):
            xs, ys = [p[0] for p in points], [p[1] for p in points]
            return {"x": int(min(xs) * inv) - 8, "y": int(min(ys) * inv) - 8,
                    "width": int((max(xs) - min(xs)) * inv) + 16, "height": int((max(ys) - min(ys)) * inv) + 16}

        return n, box([a for a, _ in pts]), box([b for _, b in pts])

    # ---------------------------------------------------------------- per-field consistency
    @staticmethod
    def _ring(gray: np.ndarray, box: BoundingBox, inner: int, outer: int) -> np.ndarray:
        h, w = gray.shape
        x0, y0 = max(0, box.x - outer), max(0, box.y - outer)
        x1, y1 = min(w, box.x + box.width + outer), min(h, box.y + box.height + outer)
        mask = np.zeros((y1 - y0, x1 - x0), bool)
        mask[:, :] = True
        ix0, iy0 = box.x - inner - x0, box.y - inner - y0
        ix1, iy1 = box.x + box.width + inner - x0, box.y + box.height + inner - y0
        mask[max(0, iy0):max(0, iy1), max(0, ix0):max(0, ix1)] = False
        return mask, (x0, y0, x1, y1)

    def field_consistency(self, img: np.ndarray, gray: np.ndarray, ex: ExtractedData,
                          ocr_items: List[Dict[str, Any]], lossless: bool) -> Tuple[List[ReasonDetail], List[PassedCheck]]:
        reasons: List[ReasonDetail] = []
        passed: List[PassedCheck] = []
        h, w = gray.shape
        flat = self.flat_mask(gray)
        residual = np.abs(gray.astype(np.int16) - cv2.medianBlur(gray, 3).astype(np.int16)).astype(np.float32)
        # Real app receipts often have subtle gradients, card shadows and resampling noise. The old 2.5/4
        # level cut-off was fitted to flat synthetic images and caused genuine screenshots to be flagged.
        tol = 7.0 if lossless else 10.0
        dark_mode = float(np.median(gray)) < 100

        # Peer statistics from all OCR text lines in the left column of the details card.
        def ink_level(b: Dict[str, int]) -> Optional[float]:
            crop = gray[b["y"]:b["y"] + b["height"], b["x"]:b["x"] + b["width"]]
            return float(np.percentile(crop, 3)) if crop.size > 50 else None

        left_items = [i for i in ocr_items if i["bbox"]["y"] > h * 0.3 and i["bbox"]["x"] < w * 0.3]
        xs = [i["bbox"]["x"] for i in left_items]
        x_mode = Counter(int(round(x / 3.0)) * 3 for x in xs).most_common(1)[0][0] if xs else None
        aligned = [x for x in xs if x_mode is not None and abs(x - x_mode) <= 4]
        dark_inks = [v for v in (ink_level(i["bbox"]) for i in left_items) if v is not None and v < 90]
        ink_ref = float(np.median(dark_inks)) if len(dark_inks) >= 3 else None

        checked = 0
        for key, label in CRITICAL_FIELDS:
            f = getattr(ex, key)
            if not f.value or not f.bbox:
                continue
            b = f.bbox
            checked += 1
            issues: List[str] = []

            # 1. Background just around the text vs slightly further out.
            near_mask, (x0, y0, x1, y1) = self._ring(gray, b, 2, 7)
            far_mask, (fx0, fy0, fx1, fy1) = self._ring(gray, b, 16, 28)
            near_px = img[y0:y1, x0:x1][near_mask & flat[y0:y1, x0:x1]]
            far_px = img[fy0:fy1, fx0:fx1][far_mask & flat[fy0:fy1, fx0:fx1]]
            bg_diff = None
            if len(near_px) > 150 and len(far_px) > 150:
                near_c, far_c = np.median(near_px, axis=0), np.median(far_px, axis=0)
                bg_diff = float(np.max(np.abs(near_c - far_c)))
                if bg_diff >= tol + 0.5:
                    reasons.append(_reason(
                        "F_BACKGROUND_MISMATCH", "HIGH", f"Patch behind the {label}",
                        f"The background right around the {label} is a slightly different colour from the area "
                        f"around it ({bg_diff:.0f} levels). This is what painting over a number and retyping it "
                        "looks like.", PENALTY["background"], field=key,
                        region={"x": b.x - 10, "y": b.y - 10, "width": b.width + 20, "height": b.height + 20},
                        value={"difference": round(bg_diff, 1)}))

            # 2. Noise inside the field vs around it.
            n_in = residual[y0:y1, x0:x1][near_mask & flat[y0:y1, x0:x1]]
            n_out = residual[fy0:fy1, fx0:fx1][far_mask & flat[fy0:fy1, fx0:fx1]]
            if len(n_in) > 150 and len(n_out) > 150:
                a, c = float(n_in.mean()), float(n_out.mean())
                if a > 1.2 and a > 3 * max(c, 0.25):
                    issues.append(f"grainy background unlike the rest of the screen (noise {a:.1f} vs {c:.1f})")

            # 3. Ink colour vs other values on the card. Dark-text-on-light only: in dark mode the darkest pixels
            # are the background, not the ink.
            if ink_ref is not None and key != "amount" and not dark_mode:
                ink = ink_level(b.model_dump())
                if ink is not None and ink < 120 and abs(ink - ink_ref) > (10 if lossless else 16):
                    issues.append(f"text colour differs from the other details ({ink:.0f} vs {ink_ref:.0f})")

            # 4. Left alignment vs other values on the card.
            if key != "amount" and x_mode is not None and len(aligned) >= 4 and b.x < w * 0.3:
                dx = b.x - x_mode
                # A retyped value sits a few pixels off its column. A large offset is just a different column
                # (labels on the left, values indented beside an icon), not an edit.
                if max(5, int(w * 0.005)) < abs(dx) <= int(w * 0.03):
                    issues.append(f"starts {abs(dx)} px out of line with the other details")

            # A few pixels of offset, or a slightly different grey, also happen on genuine screens (OCR boxes
            # start at each glyph's edge; apps colour labels and values differently). Either alone is not
            # evidence; a grainy patch is, and so are two signs on the same field.
            grainy = any(i.startswith("grainy") for i in issues)
            if grainy or len(issues) >= 2:
                reasons.append(_reason(
                    "F_TEXT_REGION_INCONSISTENT", "HIGH", f"The {label} looks retyped",
                    f"Compared with the rest of the receipt, the {label} has " + "; ".join(issues) + ".",
                    PENALTY["text_region"], field=key,
                    region={"x": b.x - 6, "y": b.y - 6, "width": b.width + 12, "height": b.height + 12}))

        if checked and not any(r.code in ("F_BACKGROUND_MISMATCH", "F_TEXT_REGION_INCONSISTENT") for r in reasons):
            passed.append(PassedCheck(code="F_FIELDS_CONSISTENT", layer="forensics",
                                      title="Amount, UTR, date and receiver show no signs of retyping"))
        return reasons, passed

    # ---------------------------------------------------------------- text compression history
    @staticmethod
    def text_trace(img: np.ndarray, gray: np.ndarray, b: Dict[str, int]) -> Optional[float]:
        """Re-compression error on a text line's strokes, per unit of contrast, or None for unusable lines.

        Text that has been through every save of the screenshot has settled; text typed on later has been
        compressed fewer times and loses more when saved again. Only dark, neutral text is comparable:
        coloured text (links, buttons) carries more chroma error by nature. Works on a crop aligned to the
        16 px JPEG block grid, so the result matches a full-image ELA without its memory cost."""
        h, w = gray.shape
        x0, y0 = max(0, b["x"]), max(0, b["y"])
        x1, y1 = min(w, b["x"] + b["width"]), min(h, b["y"] + b["height"])
        if y1 - y0 < 10 or x1 - x0 < 12:
            return None
        cx0, cy0 = max(0, (x0 - 8) // 16 * 16), max(0, (y0 - 8) // 16 * 16)
        cx1, cy1 = min(w, -(-(x1 + 8) // 16) * 16), min(h, -(-(y1 + 8) // 16) * 16)
        crop = img[cy0:cy1, cx0:cx1]
        ok, enc = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if not ok:
            return None
        ela = cv2.cvtColor(cv2.absdiff(crop, cv2.imdecode(enc, cv2.IMREAD_COLOR)), cv2.COLOR_BGR2GRAY)
        gc = gray[cy0:cy1, cx0:cx1]
        mag = np.hypot(cv2.Sobel(gc, cv2.CV_32F, 1, 0), cv2.Sobel(gc, cv2.CV_32F, 0, 1))
        inner = (slice(y0 - cy0, y1 - cy0), slice(x0 - cx0, x1 - cx0))
        g, m, e = gray[y0:y1, x0:x1], mag[inner], ela[inner].astype(np.float32)
        edge = m > np.percentile(m, 85)
        if edge.sum() < 30:
            return None
        dark = g <= np.percentile(g, 8)
        ink = img[y0:y1, x0:x1][dark].astype(np.float32)
        if float(np.median(g[dark])) > 110 or float(np.median(ink.max(axis=1) - ink.min(axis=1))) > 40:
            return None
        contrast = float(np.percentile(g, 97) - np.percentile(g, 3)) + 1.0
        if contrast < 80:
            return None
        return float(e[edge].mean() / contrast * 100.0)

    def text_history(self, img: np.ndarray, gray: np.ndarray, ex: ExtractedData,
                     ocr_items: List[Dict[str, Any]]) -> Tuple[List[ReasonDetail], List[PassedCheck], Dict[str, Any]]:
        fields = [(k, lbl) for k, lbl in TRACE_FIELDS if getattr(ex, k).value and getattr(ex, k).bbox]
        field_boxes = {k: getattr(ex, k).bbox.model_dump() for k, _ in fields}
        peers = []
        for it in ocr_items:
            if any(it["bbox"] == fb for fb in field_boxes.values()):
                continue
            v = self.text_trace(img, gray, it["bbox"])
            if v is not None:
                peers.append(v)
        info: Dict[str, Any] = {"peers": len(peers)}
        if len(peers) < 5:
            return [], [], info
        med = float(np.median(peers))
        spread = max(1.4826 * float(np.median(np.abs(np.array(peers) - med))), 0.08 * med)
        limit = max(med * TRACE_RATIO, med + 4 * spread, float(np.max(peers)) * 1.15)
        info.update({"median": round(med, 2), "limit": round(limit, 2)})
        reasons: List[ReasonDetail] = []
        for key, label in fields:
            v = self.text_trace(img, gray, field_boxes[key])
            if v is None:
                continue
            info[key] = round(v, 2)
            if v > limit:
                b = field_boxes[key]
                reasons.append(_reason(
                    "F_TEXT_ADDED_LATER", "HIGH", f"The {label} was typed on later",
                    f"The {label} carries a different compression history from the rest of the text "
                    f"({v / med:.1f}× the usual level). Text added in an editor after the screenshot was taken "
                    "looks like this.", PENALTY["added_text"] + (10 if key in ("amount", "utr") else 0),
                    field="receiver_upi_id" if key == "receiver" else key,
                    region={"x": b["x"] - 6, "y": b["y"] - 6, "width": b["width"] + 12, "height": b["height"] + 12},
                    value={"level": round(v, 2), "usual": round(med, 2)}))
        passed = [] if reasons else [PassedCheck(code="F_TEXT_HISTORY_UNIFORM", layer="forensics",
                                                 title="All text shares the same compression history")]
        return reasons, passed, info

    # ---------------------------------------------------------------- orchestration
    def analyze(self, data: bytes, img: np.ndarray, ex: ExtractedData, ocr_items: List[Dict[str, Any]],
                heatmap_path: Optional[str]) -> Dict[str, Any]:
        file_info = self.inspect_file(data)
        reasons: List[ReasonDetail] = list(file_info["reasons"])
        passed: List[PassedCheck] = list(file_info["passed"])
        lossless = file_info["format"] in ("PNG", "WEBP", "BMP")
        jpeg_q = file_info["jpeg_quality"]
        unreliable = jpeg_q is not None and jpeg_q < 50
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        if not unreliable:
            fr, fp = self.field_consistency(img, gray, ex, ocr_items, lossless)
            reasons += fr
            passed += fp

        trace_info: Dict[str, Any] = {}
        if not unreliable:
            tr, tp, trace_info = self.text_history(img, gray, ex, ocr_items)
            reasons += tr
            passed += tp

        ela = self.ela_map(img)
        ela_regions = [] if unreliable else self.ela_anomalies(img, gray, ela)
        if ela_regions:
            reasons.append(_reason(
                "F_ELA_LOCAL_ANOMALY", "HIGH", "Compression traces differ in part of the image",
                f"Error level analysis found {len(ela_regions)} area(s) that compress differently from the rest of "
                "the screenshot, typical of pasted or painted regions. See the heatmap.", PENALTY["ela"],
                region=ela_regions[0], value={"regions": ela_regions}))
        elif not unreliable:
            passed.append(PassedCheck(code="F_ELA_UNIFORM", layer="forensics",
                                      title="Compression is uniform across the image (ELA)"))

        n, src, dst = (self.copy_move(gray, lossless, [i["bbox"] for i in ocr_items]) if not unreliable
                       else (0, None, None))
        # Keep a low sensitivity threshold for a warning, but the result is non-critical because UI artwork
        # can naturally repeat visual features. This detector is a supporting signal, not an automatic verdict.
        threshold = 28
        if n >= threshold and src and dst:
            reasons.append(_reason(
                "F_COPY_MOVE", "LOW", "Weak repeated-pattern signal",
                f"An area of the screenshot resembles another area ({n} matching blocks). App icons, backgrounds, "
                "and normal UI elements can produce such matches. This is a weak clue only and must not be treated "
                "as proof of editing or used alone to label the screenshot fake.",
                PENALTY["copy_move"], region=dst, value={"source": src, "target": dst, "blocks": n}))
        elif not unreliable:
            passed.append(PassedCheck(code="F_NO_COPY_MOVE", layer="forensics",
                                      title="No copied-and-pasted regions found"))

        if heatmap_path:
            try:
                self.render_heatmap(img, ela, [r.region for r in reasons if r.region], heatmap_path)
            except Exception as e:  # pragma: no cover
                log.warning("heatmap failed: %s", e)
                heatmap_path = None

        penalty = min(MAX_FORENSIC_PENALTY, sum(r.penalty for r in reasons))
        return {
            "reasons": reasons,
            "passed": passed,
            "penalty": penalty,
            "heatmap_path": heatmap_path,
            "summary": {"format": file_info["format"], "jpeg_quality": jpeg_q, "software": file_info["software"],
                        "camera": file_info["camera"], "copy_move_blocks": n, "ela_regions": len(ela_regions),
                        "text_trace": trace_info},
        }


forensic_engine = ForensicEngine()
