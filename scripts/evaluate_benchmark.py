"""Run the full pipeline over the synthetic dataset and report precision, recall and a confusion matrix.

    python scripts/evaluate_benchmark.py [--dataset backend/storage/dataset]

Positive class = tampered. A sample counts as flagged when the verdict is SUSPICIOUS or LIKELY FAKE.
Results are written to backend/storage/benchmark_results.json and shown on the /benchmark page.
These are results on our own synthetic test set, not a measure of real-world accuracy.
"""
import argparse
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import _bootstrap

from app.config import settings
from app.services.ocr_engine import ocr_engine
from app.services.pipeline import MerchantProfile, PipelineError, analyze_image, compose_verdict

FLAGGED = {"SUSPICIOUS", "LIKELY FAKE"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", type=Path, default=settings.DATASET_DIR)
    ap.add_argument("--out", type=Path, default=settings.BENCHMARK_PATH)
    args = ap.parse_args()

    manifest_path = args.dataset / "manifest.json"
    if not manifest_path.exists():
        print("No dataset found. Run: python scripts/generate_dataset.py", file=sys.stderr)
        return 1
    meta = json.loads(manifest_path.read_text(encoding="utf-8"))
    m = meta["merchant"]
    merchant = MerchantProfile(m["name"], m["upi_id"], m["allowed_window_minutes"], m["strictness"])
    # Evaluate "as of" generation time so the time-window rules see the clock the receipts were made with.
    now = datetime.fromisoformat(meta["reference_time"])

    ocr_engine.warm_up()
    rows = []
    for s in meta["samples"]:
        data = (args.dataset / s["filename"]).read_bytes()
        try:
            a = analyze_image(data, merchant, now=now)
            v = compose_verdict(a.rule_reasons + a.forensic_reasons, merchant.strictness)
            verdict, score, reasons, secs = v.verdict, v.risk_score, v.reasons, a.timings["total"]
        except PipelineError as e:
            # The app refuses to give a verdict on unreadable images; count that as "not passed".
            verdict, score, reasons, secs = "UNREADABLE", 0.0, [], 0.0
            print(f"  {s['id']}: {e.code} {e.message}")
        flagged = verdict in FLAGGED or verdict == "UNREADABLE"
        rows.append({
            "id": s["id"], "filename": s["filename"], "label": s["label"], "tamper_type": s["tamper_type"],
            "description": s.get("description"), "verdict": verdict, "risk_score": score,
            "predicted_tampered": flagged, "top_reason": reasons[0].title if reasons else None,
            "reasons": [r.title for r in reasons], "codes": [r.code for r in reasons],
            "layers": sorted({r.layer for r in reasons}), "processing_time": round(secs, 3),
        })
        mark = "ok" if flagged == (s["label"] == "tampered") else "XX"
        print(f"{mark} {s['id']:10} {s['tamper_type']:18} {verdict:15} {score:5.0f}  "
              f"{', '.join(r.code for r in reasons) or '-'}", flush=True)

    tp = sum(r["label"] == "tampered" and r["predicted_tampered"] for r in rows)
    fn = sum(r["label"] == "tampered" and not r["predicted_tampered"] for r in rows)
    fp = sum(r["label"] == "clean" and r["predicted_tampered"] for r in rows)
    tn = sum(r["label"] == "clean" and not r["predicted_tampered"] for r in rows)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    accuracy = (tp + tn) / len(rows)
    latencies = [r["processing_time"] for r in rows if r["processing_time"]]
    per_tamper = defaultdict(lambda: {"detected": 0, "total": 0})
    for r in rows:
        if r["label"] == "tampered":
            per_tamper[r["tamper_type"]]["total"] += 1
            per_tamper[r["tamper_type"]]["detected"] += int(r["predicted_tampered"])

    result = {
        "dataset_name": meta["dataset_name"], "description": meta["description"],
        "generated_at": meta["generated_at"], "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "decision_rule": "Flagged = verdict SUSPICIOUS or LIKELY FAKE. Positive class = tampered.",
        "note": "Results on our own synthetic test set of mock receipts. Not a measure of real-world accuracy.",
        "total_samples": len(rows), "clean_samples": tn + fp, "tampered_samples": tp + fn,
        "confusion_matrix": {"true_positives": tp, "true_negatives": tn, "false_positives": fp,
                             "false_negatives": fn},
        "metrics": {"accuracy": round(accuracy * 100, 1), "precision": round(precision * 100, 1),
                    "recall": round(recall * 100, 1), "f1_score": round(f1 * 100, 1),
                    "avg_latency_seconds": round(statistics.mean(latencies), 2) if latencies else 0,
                    "max_latency_seconds": round(max(latencies), 2) if latencies else 0},
        "per_tamper": dict(per_tamper), "samples": rows,
    }
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    # Snapshot shipped with the code, so a fresh install (or Docker volume) shows results immediately.
    snapshot = Path(_bootstrap.BACKEND) / "app" / "assets" / "benchmark_results.json"
    snapshot.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("\nConfusion matrix (rows = actual, columns = predicted)")
    print(f"{'':12}{'flagged':>10}{'passed':>10}")
    print(f"{'tampered':12}{tp:>10}{fn:>10}")
    print(f"{'clean':12}{fp:>10}{tn:>10}")
    print(f"\nPrecision {precision:.1%}   Recall {recall:.1%}   F1 {f1:.1%}   Accuracy {accuracy:.1%}")
    print(f"Latency avg {result['metrics']['avg_latency_seconds']}s, max {result['metrics']['max_latency_seconds']}s")
    print("Per tamper type: " + ", ".join(f"{k} {v['detected']}/{v['total']}" for k, v in per_tamper.items()))
    print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
