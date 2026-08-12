"""Strict integrity and leakage validator for the offline YOLO dataset."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

try:
    from scripts.weighbridge_vehicle_dataset import SPLITS, dhash, hamming, parse_yolo_label, sha256
except ModuleNotFoundError:
    from weighbridge_vehicle_dataset import SPLITS, dhash, hamming, parse_yolo_label, sha256


def validate(root: Path, *, allow_incomplete: bool = False, near_duplicate_distance: int = 2) -> dict:
    errors, warnings, boxes = [], [], []
    manifest_path = root / "dataset_manifest.csv"
    with manifest_path.open(encoding="utf-8-sig", newline="") as handle:
        manifest = list(csv.DictReader(handle))
    manifest_images = {row["dataset_image"] for row in manifest}
    images: dict[Path, str] = {}
    labels: dict[Path, str] = {}
    for split in SPLITS:
        for path in (root / "images" / split).glob("*.jpg"): images[path] = split
        for path in (root / "labels" / split).glob("*.txt"): labels[path] = split
    disk_rel = {path.relative_to(root).as_posix() for path in images}
    for missing in sorted(manifest_images - disk_rel): errors.append(f"manifest image missing: {missing}")
    for orphan in sorted(disk_rel - manifest_images): errors.append(f"orphan image: {orphan}")
    positive = negative = 0
    split_counts = {split: {"images": 0, "positive": 0, "negative": 0, "missing_labels": 0} for split in SPLITS}
    for image, split in images.items():
        split_counts[split]["images"] += 1
        label = root / "labels" / split / f"{image.stem}.txt"
        if not label.exists():
            split_counts[split]["missing_labels"] += 1
            (warnings if allow_incomplete else errors).append(f"missing label: {image.relative_to(root)}")
            continue
        try:
            parsed = parse_yolo_label(label)
            boxes.extend(parsed)
            if parsed:
                positive += 1; split_counts[split]["positive"] += 1
            else:
                negative += 1; split_counts[split]["negative"] += 1
        except ValueError as exc: errors.append(str(exc))
    for label, split in labels.items():
        image = root / "images" / split / f"{label.stem}.jpg"
        if not image.exists(): errors.append(f"orphan label: {label.relative_to(root)}")
    session_splits: dict[str, set[str]] = defaultdict(set)
    for row in manifest: session_splits[row["source_session"]].add(row["split"])
    for session, split_set in session_splits.items():
        if len(split_set) > 1: errors.append(f"session leakage: {session} -> {sorted(split_set)}")
    exact: dict[str, tuple[Path, str]] = {}
    fingerprints: list[tuple[Path, str, int]] = []
    for image, split in images.items():
        digest = sha256(image)
        if digest in exact and exact[digest][1] != split:
            errors.append(f"exact duplicate leakage: {exact[digest][0].name} / {image.name}")
        else: exact[digest] = (image, split)
        fingerprints.append((image, split, dhash(image)))
    for index, (left, left_split, left_hash) in enumerate(fingerprints):
        for right, right_split, right_hash in fingerprints[index + 1:]:
            if left_split != right_split and hamming(left_hash, right_hash) <= near_duplicate_distance:
                warnings.append(f"perceptual near-duplicate across splits: {left.name} / {right.name}")
    sizes = [box[3] * box[4] for box in boxes]
    warning_count = len(warnings)
    report = {"valid": not errors, "complete": all((root / "labels" / split / f"{image.stem}.txt").exists() for image, split in images.items()),
              "images": len(images), "labeled_positive_images": positive, "labeled_negative_images": negative,
              "boxes": len(boxes), "splits": split_counts,
              "bbox_area": {"min": min(sizes) if sizes else None, "median": float(np.median(sizes)) if sizes else None,
              "max": max(sizes) if sizes else None}, "sessions_by_split": {s: sorted(k for k,v in session_splits.items() if s in v) for s in SPLITS},
              "manifest_status": dict(Counter(row["annotation_status"] for row in manifest)), "errors": errors,
              "warning_count": warning_count, "warnings": warnings[:100],
              "warnings_truncated": warning_count > 100}
    (root / "validation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("data", type=Path)
    parser.add_argument("--allow-incomplete", action="store_true"); parser.add_argument("--near-duplicate-distance", type=int, default=2)
    args = parser.parse_args(); report = validate(args.data.resolve(), allow_incomplete=args.allow_incomplete,
                                                   near_duplicate_distance=args.near_duplicate_distance)
    print(json.dumps(report, indent=2)); raise SystemExit(0 if report["valid"] else 1)


if __name__ == "__main__": main()
