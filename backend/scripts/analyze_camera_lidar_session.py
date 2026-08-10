"""Analyze one version-2 Camera + LiDAR diagnostic session directory."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def nearest_matches(lidar: list[dict], camera: list[dict]) -> list[dict]:
    frames = sorted(camera, key=lambda row: int(row["captured_monotonic_ns"]))
    result = []
    for profile in lidar:
        value = int(profile["captured_monotonic_ns"])
        nearest = min(frames, key=lambda row: abs(int(row["captured_monotonic_ns"]) - value)) if frames else None
        result.append({
            "lidar_sequence": profile.get("sequence_number"),
            "lidar_captured_utc": profile.get("captured_utc"),
            "camera_sequence": nearest.get("sequence_number") if nearest else None,
            "delta_ms": round((int(nearest["captured_monotonic_ns"]) - value) / 1_000_000, 3) if nearest else None,
        })
    return result


def _timing(rows: list[dict]) -> dict:
    values = [int(row["captured_monotonic_ns"]) for row in rows]
    intervals = [(b - a) / 1_000_000 for a, b in zip(values, values[1:])]
    duration = (values[-1] - values[0]) / 1e9 if len(values) > 1 else 0
    return {
        "count": len(rows), "duration_sec": round(duration, 6),
        "effective_hz": round((len(values) - 1) / duration, 6) if duration else None,
        "interval_ms_min": min(intervals) if intervals else None,
        "interval_ms_median": statistics.median(intervals) if intervals else None,
        "interval_ms_max": max(intervals) if intervals else None,
        "interval_jitter_stdev_ms": round(statistics.pstdev(intervals), 6) if intervals else None,
    }


def _camera_pipeline_timing(rows: list[dict]) -> dict:
    stages = {
        "http_ms": ("camera_acquisition_started_monotonic_ns", "camera_http_response_received_monotonic_ns"),
        "decode_ms": ("camera_http_response_received_monotonic_ns", "camera_decode_completed_monotonic_ns"),
        "publish_ms": ("camera_decode_completed_monotonic_ns", "frame_published_monotonic_ns"),
        "subscriber_ms": ("frame_published_monotonic_ns", "recorder_observed_monotonic_ns"),
        "queue_wait_ms": ("recorder_observed_monotonic_ns", "writer_started_monotonic_ns"),
        "writer_ms": ("writer_started_monotonic_ns", "writer_persisted_monotonic_ns"),
    }
    result = {}
    for name, (start, end) in stages.items():
        values = [
            (int(row[end]) - int(row[start])) / 1_000_000
            for row in rows if row.get(start) not in (None, "") and row.get(end) not in (None, "")
        ]
        result[f"{name}_median"] = statistics.median(values) if values else None
        result[f"{name}_max"] = max(values) if values else None
    return result


def analyze_session(session_dir: Path) -> tuple[dict, dict[str, list[dict]]]:
    manifest = json.loads((session_dir / "manifest.json").read_text(encoding="utf-8"))
    lidar = read_jsonl(session_dir / "lidar" / "raw_scans.jsonl")
    camera = read_csv(session_dir / "camera" / "frames.csv")
    events = read_jsonl(session_dir / "events.jsonl") + read_jsonl(session_dir / "markers.jsonl")
    matches = nearest_matches(lidar, camera)
    latencies = [float(row["acquisition_latency_ms"]) for row in lidar if row.get("acquisition_latency_ms") is not None]
    session_duration = None
    if manifest.get("started_at") and manifest.get("ended_at"):
        session_duration = (
            datetime.fromisoformat(manifest["ended_at"]) - datetime.fromisoformat(manifest["started_at"])
        ).total_seconds()
    duplicate_frames = sum(
        first.get("jpeg_sha256") == second.get("jpeg_sha256")
        for first, second in zip(camera, camera[1:]) if first.get("jpeg_sha256")
    )
    summary = {
        "format_version": manifest.get("format_version"), "session_key": manifest.get("session_key"),
        "trip_id": manifest.get("trip_id"), "status": manifest.get("status"),
        "session_duration_sec": session_duration,
        "lidar": {**_timing(lidar), "latency_ms_median": statistics.median(latencies) if latencies else None},
        "camera": {
            **_timing(camera),
            "adjacent_duplicate_frames": duplicate_frames,
            "pipeline": _camera_pipeline_timing(camera),
        },
        "events_count": len(events),
        "matching": {"count": len(matches), "absolute_delta_ms_median": statistics.median(abs(row["delta_ms"]) for row in matches) if matches and camera else None},
    }
    return summary, {"lidar_profiles": lidar, "camera_frames": camera, "events": events, "matches": matches}


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = sorted({key for row in rows for key in row}) or ["empty"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output = args.output_dir or args.session_dir / "analysis"
    output.mkdir(parents=True, exist_ok=True)
    summary, tables = analyze_session(args.session_dir)
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name in ("lidar_profiles", "camera_frames", "events", "matches"):
        write_csv(output / f"{name}.csv", tables[name])
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
