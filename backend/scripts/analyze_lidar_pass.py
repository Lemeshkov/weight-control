"""Offline diagnostics for persisted lidar pass JSON files.

This script is deliberately independent from the FastAPI application and hardware
clients.  It reads an existing pass file and writes reproducible timing, profile
quality and adjacent-profile similarity statistics without changing production
state or the source file.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp has no timezone: {value!r}")
    return parsed


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def _resample(values: list[float], size: int) -> list[float]:
    if size <= 0 or not values:
        return []
    if len(values) == 1:
        return values * size
    if size == 1:
        return [values[0]]
    result: list[float] = []
    for index in range(size):
        source = index * (len(values) - 1) / (size - 1)
        left = math.floor(source)
        right = math.ceil(source)
        if left == right:
            result.append(values[left])
        else:
            weight = source - left
            result.append(values[left] * (1 - weight) + values[right] * weight)
    return result


def compare_profiles(previous: Iterable[int], current: Iterable[int]) -> dict[str, float | int | None]:
    left = [float(value) for value in previous]
    right = [float(value) for value in current]
    size = min(len(left), len(right))
    if not size:
        return {"comparison_points": 0, "median_abs_delta_mm": None, "rmse_mm": None, "correlation": None}
    left = _resample(left, size)
    right = _resample(right, size)
    deltas = [a - b for a, b in zip(left, right)]
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    denominator = math.sqrt(
        sum((a - left_mean) ** 2 for a in left) * sum((b - right_mean) ** 2 for b in right)
    )
    return {
        "comparison_points": size,
        "median_abs_delta_mm": round(statistics.median(abs(value) for value in deltas), 3),
        "rmse_mm": round(math.sqrt(statistics.fmean(value * value for value in deltas)), 3),
        "correlation": round(numerator / denominator, 6) if denominator else None,
    }


def analyze_document(document: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    profiles = document.get("profiles")
    if not isinstance(profiles, list):
        raise ValueError("expected top-level 'profiles' array")
    rows: list[dict[str, Any]] = []
    timestamps: list[datetime] = []
    previous_distances: list[int] | None = None
    for index, profile in enumerate(profiles):
        if not isinstance(profile, dict):
            raise ValueError(f"profile {index} is not an object")
        captured_at = parse_timestamp(str(profile["captured_at"]))
        timestamps.append(captured_at)
        distances = [int(value) for value in profile.get("distances_mm", [])]
        comparison = compare_profiles(previous_distances or [], distances)
        rows.append(
            {
                "profile_index": index,
                "sequence_number": profile.get("sequence_number"),
                "captured_at": captured_at.isoformat(),
                "delta_time_ms": None if index == 0 else round((captured_at - timestamps[-2]).total_seconds() * 1000, 3),
                "points_total": profile.get("points_total"),
                "points_valid": profile.get("points_valid", len(distances)),
                "min_distance_mm": min(distances) if distances else None,
                "max_distance_mm": max(distances) if distances else None,
                **comparison,
            }
        )
        previous_distances = distances

    intervals = [float(row["delta_time_ms"]) for row in rows[1:] if row["delta_time_ms"] is not None]
    duration = (timestamps[-1] - timestamps[0]).total_seconds() if len(timestamps) > 1 else 0.0
    summary = {
        "profiles_count": len(rows),
        "duration_seconds": round(duration, 6),
        "effective_frequency_hz": round((len(rows) - 1) / duration, 6) if duration > 0 else None,
        "interval_ms": {
            "min": min(intervals) if intervals else None,
            "median": statistics.median(intervals) if intervals else None,
            "p95": _percentile(intervals, 0.95),
            "max": max(intervals) if intervals else None,
        },
        "points_total": [row["points_total"] for row in rows],
        "points_valid": [row["points_valid"] for row in rows],
        "geometry_reconstructable": False,
        "geometry_warning": (
            "Current pass profiles contain filtered distances without their original beam indexes or scan geometry; "
            "angle and Cartesian x/z values cannot be reconstructed exactly."
        ),
    }
    return summary, rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pass_json", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir or args.pass_json.parent / f"{args.pass_json.stem}_analysis"
    document = json.loads(args.pass_json.read_text(encoding="utf-8"))
    summary, rows = analyze_document(document)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fieldnames = list(rows[0]) if rows else ["profile_index"]
    with (output_dir / "profiles.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
