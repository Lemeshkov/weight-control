"""Clip only tiny YOLO export rounding overflow; reject material geometry errors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_TOLERANCE = 1e-5


def normalize_box(values: tuple[int, float, float, float, float], *, tolerance: float = DEFAULT_TOLERANCE):
    class_id, x, y, width, height = values
    if class_id != 0 or width <= 0 or height <= 0:
        raise ValueError("only class 0 with positive dimensions is allowed")
    xmin, ymin, xmax, ymax = x - width / 2, y - height / 2, x + width / 2, y + height / 2
    overflow = max(0.0, -xmin, -ymin, xmax - 1.0, ymax - 1.0)
    if overflow > tolerance:
        raise ValueError(f"bbox overflow {overflow:.9g} exceeds tolerance {tolerance:.9g}")
    if overflow == 0:
        return values, 0.0
    xmin, ymin, xmax, ymax = max(0.0, xmin), max(0.0, ymin), min(1.0, xmax), min(1.0, ymax)
    normalized = (class_id, (xmin + xmax) / 2, (ymin + ymax) / 2, xmax - xmin, ymax - ymin)
    if normalized[3] <= 0 or normalized[4] <= 0:
        raise ValueError("clipping produced an empty bbox")
    return normalized, overflow


def normalize_file(path: Path, *, tolerance: float = DEFAULT_TOLERANCE, apply: bool = False) -> list[dict]:
    output, changes = [], []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        parts = raw.split()
        if len(parts) != 5:
            raise ValueError(f"{path}:{line_number}: expected 5 fields")
        values = (int(parts[0]), *(float(value) for value in parts[1:]))
        normalized, overflow = normalize_box(values, tolerance=tolerance)
        if overflow:
            changes.append({"file": path.name, "line": line_number, "overflow": overflow,
                            "before": list(values), "after": list(normalized)})
            output.append(f"{normalized[0]} " + " ".join(f"{value:.9f}" for value in normalized[1:]))
        else:
            output.append(raw)  # Preserve every byte of already-valid bbox geometry.
    if apply and changes:
        path.write_text("\n".join(output) + "\n", encoding="utf-8")
    return changes


def normalize_directory(labels: Path, *, tolerance: float = DEFAULT_TOLERANCE, apply: bool = False) -> dict:
    changes, errors = [], []
    for path in sorted(labels.glob("*.txt")):
        try:
            changes.extend(normalize_file(path, tolerance=tolerance, apply=apply))
        except (ValueError, TypeError) as exc:
            errors.append(str(exc))
    return {"mode": "APPLY" if apply else "DRY_RUN", "labels": str(labels), "tolerance": tolerance,
            "clipped_boxes": len(changes), "changes": changes, "errors": errors}


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("labels", type=Path)
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE); parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(); report = normalize_directory(args.labels.resolve(), tolerance=args.tolerance, apply=args.apply)
    print(json.dumps(report, indent=2)); raise SystemExit(1 if report["errors"] else 0)


if __name__ == "__main__": main()
