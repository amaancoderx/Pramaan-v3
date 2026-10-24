import logging
import threading
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from app.config import settings

log = logging.getLogger("pramaan.ocr")

# OCR runs on a downscaled copy; phone screenshots stay legible at this width and it is several times faster.
OCR_WIDTH = 1100


class OCREngine:
    """RapidOCR (PP-OCRv4 via onnxruntime) with a pytesseract fallback. Boxes are returned in original pixels."""

    def __init__(self) -> None:
        self._ocr = None
        self._name = "unavailable"
        self._lock = threading.Lock()
        self._initialized = False

    @property
    def name(self) -> str:
        return self._name

    def warm_up(self) -> None:
        engine = self._get()
        if engine is not None:
            try:
                engine(np.full((64, 256, 3), 255, np.uint8))
            except Exception:  # pragma: no cover - warm-up is best effort
                pass

    def _get(self):
        if not self._initialized:
            with self._lock:
                if not self._initialized and settings.OCR_ENGINE == "tesseract":
                    self._ocr, self._name, self._initialized = None, "tesseract", True
                if not self._initialized:
                    try:
                        from rapidocr_onnxruntime import RapidOCR
                        self._ocr = RapidOCR(det_limit_type="max", det_limit_side_len=960, use_cls=False,
                                             **({"intra_op_num_threads": settings.OCR_THREADS} if settings.OCR_THREADS else {}))
                        self._name = "rapidocr-onnxruntime"
                    except Exception as e:  # pragma: no cover
                        log.warning("RapidOCR unavailable (%s); falling back to tesseract", e)
                        self._ocr = None
                        self._name = "tesseract"
                    self._initialized = True
        return self._ocr

    @staticmethod
    def check_image_quality(img: Optional[np.ndarray]) -> Tuple[bool, Optional[str]]:
        if img is None or img.size == 0:
            return False, "The file could not be read as an image."
        h, w = img.shape[:2]
        if min(h, w) < settings.MIN_IMAGE_DIMENSION:
            return False, f"Image is too small ({w}x{h} px). Send the full phone screenshot, not a thumbnail."
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
        scale = OCR_WIDTH / w if w > OCR_WIDTH else 1.0
        if scale < 1:
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        focus = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        if focus < settings.MIN_FOCUS_SCORE:
            return False, (f"Image quality too low: the screenshot is too blurry to read reliably "
                           f"(focus score {focus:.0f}). Ask for the original screenshot instead of a photo.")
        return True, None

    @staticmethod
    def _scaled_view(img: np.ndarray) -> Tuple[np.ndarray, float]:
        h, w = img.shape[:2]
        scale = min(1.25, OCR_WIDTH / max(w, 1))
        view = cv2.resize(img, None, fx=scale, fy=scale,
                          interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA) if scale != 1 else img
        return view, scale

    def _rapid_items(self, engine, view: np.ndarray, scale: float) -> List[Dict[str, Any]]:
        inv = 1.0 / scale
        with self._lock:
            out, _ = engine(view)
        items: List[Dict[str, Any]] = []
        for pts, text, score in out or []:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            x0, y0 = int(min(xs) * inv), int(min(ys) * inv)
            x1, y1 = int(max(xs) * inv), int(max(ys) * inv)
            items.append({
                "text": str(text).strip(),
                "confidence": round(float(score), 4),
                "bbox": {"x": max(0, x0), "y": max(0, y0), "width": max(1, x1 - x0), "height": max(1, y1 - y0)},
            })
        return items

    @staticmethod
    def _merge_passes(first: List[Dict[str, Any]], second: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Combine OCR views while deduplicating the same line detected in both passes."""
        merged = list(first)

        def iou(a, b):
            ax0, ay0 = a["x"], a["y"]
            ax1, ay1 = ax0 + a["width"], ay0 + a["height"]
            bx0, by0 = b["x"], b["y"]
            bx1, by1 = bx0 + b["width"], by0 + b["height"]
            area = max(0, min(ax1, bx1) - max(ax0, bx0)) * max(0, min(ay1, by1) - max(ay0, by0))
            union = a["width"] * a["height"] + b["width"] * b["height"] - area
            return area / union if union else 0.0

        def norm(t):
            return "".join(ch.lower() for ch in t if ch.isalnum())

        for candidate in second:
            duplicate_index = None
            for idx, existing in enumerate(merged):
                overlap = iou(existing["bbox"], candidate["bbox"])
                same_text = norm(existing["text"]) == norm(candidate["text"])
                same_location = overlap >= 0.42
                if same_text and (same_location or overlap >= 0.12):
                    duplicate_index = idx
                    break
                if same_location and overlap >= 0.58:
                    duplicate_index = idx
                    break
            if duplicate_index is None:
                merged.append(candidate)
                continue
            existing = merged[duplicate_index]
            current = norm(existing["text"])
            incoming = norm(candidate["text"])
            # Prefer a longer reading when it contains the other reading and confidence is comparable;
            # otherwise keep the more confident OCR result for the same visual region.
            if incoming and current and (incoming in current or current in incoming) and abs(
                candidate["confidence"] - existing["confidence"]
            ) < 0.18:
                if len(candidate["text"]) > len(existing["text"]):
                    merged[duplicate_index] = candidate
            elif candidate["confidence"] > existing["confidence"]:
                merged[duplicate_index] = candidate
        return [i for i in merged if i["text"]]

    @staticmethod
    def _offset_items(items: List[Dict[str, Any]], y_offset: int) -> List[Dict[str, Any]]:
        """Map OCR boxes from a vertical crop back to the coordinates of the full screenshot."""
        mapped = []
        for source in items:
            item = {**source, "bbox": dict(source["bbox"])}
            item["bbox"]["y"] += y_offset
            mapped.append(item)
        return mapped

    def _run_view(self, engine, img: np.ndarray, y_offset: int = 0) -> List[Dict[str, Any]]:
        view, scale = self._scaled_view(img)
        if engine is not None:
            found = self._rapid_items(engine, view, scale)
        else:
            found = self._tesseract(view, 1.0 / scale)
        return self._offset_items(found, y_offset) if y_offset else found

    def extract(self, img: np.ndarray) -> List[Dict[str, Any]]:
        """OCR the full screenshot and overlapping vertical crops to preserve small receipt text.

        A full tall phone screenshot gets scaled heavily by text detectors with a maximum-side limit.
        Overlapping crops let the receiver/UTR/date fields in the lower half be read at much larger size.
        """
        engine = self._get()
        primary: List[Dict[str, Any]] = []
        try:
            primary = self._run_view(engine, img)
            h, w = img.shape[:2]
            passes = [primary]
            if settings.OCR_LIGHT:
                return self._finish(primary, img)

            # Contrast-enhanced full view can recover pale text on dark/saturated receipt panels.
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
            enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
            enhanced = cv2.convertScaleAbs(enhanced, alpha=1.12, beta=3)
            enhanced_bgr = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
            passes.append(self._run_view(engine, enhanced_bgr))

            # Overlapping bands are especially useful for long Android/iOS transaction detail screens.
            if h >= int(w * 1.35):
                for top_frac, bottom_frac in ((0.00, 0.48), (0.27, 0.76), (0.52, 1.00)):
                    y0 = max(0, int(h * top_frac))
                    y1 = min(h, max(y0 + 1, int(h * bottom_frac)))
                    passes.append(self._run_view(engine, img[y0:y1, :], y_offset=y0))

                # One local-contrast lower band targets often faint banking name, UTR and timestamp rows.
                y0 = int(h * 0.44)
                lower = img[y0:h, :]
                lower_gray = cv2.cvtColor(lower, cv2.COLOR_BGR2GRAY) if lower.ndim == 3 else lower
                lower_gray = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(lower_gray)
                lower_gray = cv2.convertScaleAbs(lower_gray, alpha=1.18, beta=5)
                lower_bgr = cv2.cvtColor(lower_gray, cv2.COLOR_GRAY2BGR)
                passes.append(self._run_view(engine, lower_bgr, y_offset=y0))

            items = passes[0]
            for candidate_pass in passes[1:]:
                items = self._merge_passes(items, candidate_pass)
        except Exception as e:  # pragma: no cover
            log.error("OCR pass failed: %s", e)
            items = primary

        return self._finish(items, img)

    @staticmethod
    def _finish(items: List[Dict[str, Any]], img: np.ndarray) -> List[Dict[str, Any]]:
        h, w = img.shape[:2]
        items = [i for i in items if i["text"] and i["bbox"]["x"] < w and i["bbox"]["y"] < h]
        items.sort(key=lambda i: (i["bbox"]["y"], i["bbox"]["x"]))
        return items

    @staticmethod
    def _tesseract(img: np.ndarray, inv: float) -> List[Dict[str, Any]]:  # pragma: no cover - fallback path
        try:
            import pytesseract
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        except Exception as e:
            log.error("Tesseract unavailable: %s", e)
            return []
        lines: Dict[Tuple[int, int, int], Dict[str, Any]] = {}
        for i, txt in enumerate(data["text"]):
            conf = float(data["conf"][i])
            if not txt.strip() or conf < 0:
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            x, y, bw, bh = (int(data[k][i] * inv) for k in ("left", "top", "width", "height"))
            ln = lines.setdefault(key, {"words": [], "confs": [], "x0": x, "y0": y, "x1": x + bw, "y1": y + bh})
            ln["words"].append(txt.strip())
            ln["confs"].append(conf / 100)
            ln["x0"], ln["y0"] = min(ln["x0"], x), min(ln["y0"], y)
            ln["x1"], ln["y1"] = max(ln["x1"], x + bw), max(ln["y1"], y + bh)
        return [{
            "text": " ".join(ln["words"]),
            "confidence": round(sum(ln["confs"]) / len(ln["confs"]), 4),
            "bbox": {"x": ln["x0"], "y": ln["y0"], "width": ln["x1"] - ln["x0"], "height": ln["y1"] - ln["y0"]},
        } for ln in lines.values()]


ocr_engine = OCREngine()
