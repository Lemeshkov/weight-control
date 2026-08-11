"""Shared, production-independent helpers for the one-class research dataset."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import cv2

CLASS_NAME = "weighbridge_vehicle"
SPLITS = ("train", "val", "test")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_frames(session: Path) -> list[dict[str, Any]]:
    with (session / "camera" / "frames.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result = []
    for row in rows:
        source = session / "camera" / row["file"]
        if source.exists():
            result.append({**row, "timestamp_ns": int(row["captured_monotonic_ns"]), "source": source})
    return result


def presence_markers(session: Path) -> dict[str, int]:
    found: dict[str, int] = {}
    for record in read_jsonl(session / "markers.jsonl"):
        label = record.get("payload", {}).get("label")
        if label in {"VEHICLE_ENTERED", "STOPPED", "RESUMED", "VEHICLE_EXITED"}:
            found[label] = int(record["captured_monotonic_ns"])
    return found


def dhash(path: Path) -> int:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"Unreadable image: {path}")
    small = cv2.resize(image, (9, 8), interpolation=cv2.INTER_AREA)
    bits = small[:, 1:] > small[:, :-1]
    value = 0
    for bit in bits.flat:
        value = (value << 1) | int(bit)
    return value


def hamming(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def select_diverse(rows: list[dict[str, Any]], limit: int, *, min_gap_ms: int = 600,
                   min_hash_distance: int = 4) -> list[dict[str, Any]]:
    """Even temporal coverage with local perceptual duplicate suppression."""
    if limit <= 0 or not rows:
        return []
    ordered = sorted(rows, key=lambda row: row["timestamp_ns"])
    indexes = sorted({round(i * (len(ordered) - 1) / max(limit - 1, 1)) for i in range(limit)})
    candidates = [ordered[index] for index in indexes]
    selected: list[dict[str, Any]] = []
    last_timestamp = -10**30
    hashes: list[int] = []
    for row in candidates:
        fingerprint = dhash(row["source"])
        gap_ms = (row["timestamp_ns"] - last_timestamp) / 1e6
        if selected and gap_ms < min_gap_ms and hamming(fingerprint, hashes[-1]) < min_hash_distance:
            continue
        selected.append(row)
        hashes.append(fingerprint)
        last_timestamp = row["timestamp_ns"]
    return selected


def parse_yolo_label(path: Path) -> list[tuple[int, float, float, float, float]]:
    boxes = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        parts = raw.split()
        if len(parts) != 5:
            raise ValueError(f"{path}:{line_number}: expected 5 fields")
        try:
            class_id = int(parts[0]); x, y, width, height = map(float, parts[1:])
        except ValueError as exc:
            raise ValueError(f"{path}:{line_number}: non-numeric YOLO label") from exc
        if class_id != 0:
            raise ValueError(f"{path}:{line_number}: only class 0 is allowed")
        if width <= 0 or height <= 0:
            raise ValueError(f"{path}:{line_number}: bbox dimensions must be positive")
        if not all(0 <= value <= 1 for value in (x, y, width, height)):
            raise ValueError(f"{path}:{line_number}: coordinates must be normalized")
        if x - width / 2 < 0 or x + width / 2 > 1 or y - height / 2 < 0 or y + height / 2 > 1:
            raise ValueError(f"{path}:{line_number}: bbox extends outside image")
        boxes.append((class_id, x, y, width, height))
    return boxes


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader(); writer.writerows(rows)
