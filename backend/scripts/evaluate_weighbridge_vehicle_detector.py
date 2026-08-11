"""Presence/gap/continuity evaluation for a trained one-class detector."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

import cv2
import numpy as np

try:
    from scripts.weighbridge_vehicle_dataset import write_csv
    from scripts.validate_weighbridge_vehicle_dataset import validate
except ModuleNotFoundError:
    from weighbridge_vehicle_dataset import write_csv
    from validate_weighbridge_vehicle_dataset import validate

RECALL_GATE = .90
NEGATIVE_FALSE_POSITIVE_RATE_GATE = .02
MAXIMUM_MISSED_DURATION_MS_GATE = 1000


def presence_metrics(rows: list[dict]) -> dict:
    positives = [r for r in rows if r["ground_truth_present"]]
    negatives = [r for r in rows if not r["ground_truth_present"]]
    tp = sum(r["detected"] for r in positives); fp = sum(r["detected"] for r in negatives)
    missed_runs, current = [], []
    for row in sorted(positives, key=lambda r: (r["source_session"], r["timestamp_ns"])):
        if not row["detected"]: current.append(row)
        elif current: missed_runs.append(current); current = []
    if current: missed_runs.append(current)
    durations = [(run[-1]["timestamp_ns"] - run[0]["timestamp_ns"]) / 1e6 for run in missed_runs]
    centers = [(r["center_x"], r["center_y"]) for r in rows if r["detected"]]
    jumps = [float(np.hypot(b[0]-a[0], b[1]-a[1])) for a,b in zip(centers, centers[1:])]
    recall = tp / len(positives) if positives else None; precision = tp / (tp + fp) if tp + fp else None
    fpr = fp / len(negatives) if negatives else None; longest = max(durations, default=0)
    return {"presence_recall": recall, "presence_precision": precision, "negative_false_positive_rate": fpr,
            "positive_frames": len(positives), "negative_frames": len(negatives), "true_positive_frames": tp,
            "false_positive_frames": fp, "longest_missed_frame_run": max((len(r) for r in missed_runs), default=0),
            "longest_missed_duration_ms": longest, "bbox_center_jump_median": float(np.median(jumps)) if jumps else None,
            "confidence_median": float(np.median([r["confidence"] for r in rows if r["detected"]])) if any(r["detected"] for r in rows) else None,
            "tracking_research_gate": bool(recall is not None and recall >= RECALL_GATE and fpr is not None and
                                             fpr <= NEGATIVE_FALSE_POSITIVE_RATE_GATE and longest <= MAXIMUM_MISSED_DURATION_MS_GATE)}


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("data", type=Path); parser.add_argument("weights", type=Path)
    parser.add_argument("--split", choices=("val", "test"), default="test"); parser.add_argument("--conf", type=float, default=.25)
    parser.add_argument("--output", type=Path, default=Path("../diagnostics/training/weighbridge_vehicle/evaluation"))
    args = parser.parse_args(); root = args.data.resolve().parent; report = validate(root)
    if not report["valid"] or not report["complete"]: raise SystemExit("Strict dataset validation failed; evaluation refused.")
    from ultralytics import YOLO
    with (root / "dataset_manifest.csv").open(encoding="utf-8-sig", newline="") as handle:
        manifest = {r["dataset_image"]: r for r in csv.DictReader(handle)}
    output = args.output.resolve(); preview = output / "annotated_test"; preview.mkdir(parents=True, exist_ok=True)
    model = YOLO(str(args.weights.resolve())); rows = []
    for image in sorted((root / "images" / args.split).glob("*.jpg")):
        rel = image.relative_to(root).as_posix(); meta = manifest[rel]
        label = root / "labels" / args.split / f"{image.stem}.txt"; present = bool(label.read_text(encoding="utf-8").strip())
        result = model.predict(str(image), conf=args.conf, classes=[0], verbose=False)[0]
        boxes = result.boxes; detected = len(boxes) > 0
        confidence = float(boxes.conf.max().item()) if detected else 0.0
        center_x = center_y = None
        if detected:
            best = int(boxes.conf.argmax().item()); xywhn = boxes.xywhn[best].cpu().numpy()
            center_x, center_y = float(xywhn[0]), float(xywhn[1])
        rows.append({"image": rel, "source_session": meta["source_session"], "timestamp_ns": int(meta["timestamp"]),
                     "ground_truth_present": present, "detected": detected, "confidence": confidence,
                     "center_x": center_x, "center_y": center_y})
        cv2.imwrite(str(preview / image.name), result.plot())
    metrics = presence_metrics(rows); metrics.update({"split": args.split, "confidence_threshold": args.conf,
        "gates": {"presence_recall_min": RECALL_GATE, "negative_false_positive_rate_max": NEGATIVE_FALSE_POSITIVE_RATE_GATE,
                  "longest_missed_duration_ms_max": MAXIMUM_MISSED_DURATION_MS_GATE},
        "warning": "Current TEST sessions are development data, not UNSEEN_VALIDATION."})
    output.mkdir(parents=True, exist_ok=True); write_csv(output / "detection_evaluation.csv", rows, list(rows[0]) if rows else ["image"])
    (output / "detection_evaluation.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8"); print(json.dumps(metrics, indent=2))


if __name__ == "__main__": main()
