"""Offline Camera/LiDAR motion experiment for a version-2 diagnostic session."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np


VALID_MARKERS = {"STOPPED", "RESUMED"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def parse_markers(path: Path) -> dict[str, int]:
    result: dict[str, int] = {}
    for record in read_jsonl(path):
        label = str(record.get("payload", {}).get("label", record.get("label", ""))).upper()
        if label in VALID_MARKERS:
            if label in result:
                raise ValueError(f"duplicate {label} marker")
            result[label] = int(record["captured_monotonic_ns"])
    missing = VALID_MARKERS - result.keys()
    if missing:
        raise ValueError(f"missing operator markers: {sorted(missing)}")
    if result["RESUMED"] <= result["STOPPED"]:
        raise ValueError("RESUMED marker must follow STOPPED")
    return result


def load_frame_rows(session_dir: Path, verify_hashes: bool = True) -> list[dict[str, Any]]:
    with (session_dir / "camera" / "frames.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows.sort(key=lambda row: int(row["captured_monotonic_ns"]))
    timestamps = [int(row["captured_monotonic_ns"]) for row in rows]
    if any(right <= left for left, right in zip(timestamps, timestamps[1:])):
        raise ValueError("camera timestamps are not strictly increasing")
    for row in rows:
        path = session_dir / "camera" / row["file"]
        if not path.is_file():
            raise FileNotFoundError(path)
        if verify_hashes and row.get("jpeg_sha256"):
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != row["jpeg_sha256"]:
                raise ValueError(f"SHA-256 mismatch: {path.name}")
        row["path"] = str(path)
        row["captured_monotonic_ns"] = int(row["captured_monotonic_ns"])
    return rows


def normalized_polygon_mask(shape: tuple[int, int], polygon: list[list[float]] | None) -> np.ndarray | None:
    if not polygon:
        return None
    height, width = shape
    points = np.array([
        [round(max(0.0, min(1.0, x)) * (width - 1)), round(max(0.0, min(1.0, y)) * (height - 1))]
        for x, y in polygon
    ], dtype=np.int32)
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(mask, [points], 255)
    return mask


def robust_track_metrics(vectors: np.ndarray, dt_seconds: float) -> dict[str, float | int]:
    if len(vectors) == 0:
        return {key: 0 for key in (
            "tracks_valid", "median_dx", "median_dy", "median_magnitude",
            "p75_magnitude", "p90_magnitude", "direction_consistency", "motion_score",
        )}
    magnitudes = np.linalg.norm(vectors, axis=1)
    median_vector = np.median(vectors, axis=0)
    norm = float(np.linalg.norm(median_vector))
    direction = median_vector / norm if norm else np.array([1.0, 0.0])
    projections = vectors @ direction
    consistency = float(max(np.mean(projections >= 0), np.mean(projections <= 0)))
    median_magnitude = float(np.median(magnitudes))
    return {
        "tracks_valid": int(len(vectors)),
        "median_dx": float(np.median(vectors[:, 0])),
        "median_dy": float(np.median(vectors[:, 1])),
        "median_magnitude": median_magnitude,
        "p75_magnitude": float(np.percentile(magnitudes, 75)),
        "p90_magnitude": float(np.percentile(magnitudes, 90)),
        "direction_consistency": consistency,
        "motion_score": median_magnitude / max(dt_seconds, 1e-6),
    }


def lk_pair(previous: np.ndarray, current: np.ndarray, dt_seconds: float, mask=None, clahe=True) -> tuple[dict, np.ndarray]:
    if clahe:
        enhancer = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        previous = enhancer.apply(previous); current = enhancer.apply(current)
    features = cv2.goodFeaturesToTrack(previous, maxCorners=400, qualityLevel=0.01, minDistance=7, mask=mask)
    detected = 0 if features is None else len(features)
    if not detected:
        return {"features_detected": 0, **robust_track_metrics(np.empty((0, 2)), dt_seconds), "quality": 0.0}, np.empty((0, 2))
    forward, status_forward, _ = cv2.calcOpticalFlowPyrLK(previous, current, features, None, winSize=(21, 21), maxLevel=3)
    backward, status_backward, _ = cv2.calcOpticalFlowPyrLK(current, previous, forward, None, winSize=(21, 21), maxLevel=3)
    valid = (status_forward.ravel() == 1) & (status_backward.ravel() == 1)
    fb_error = np.linalg.norm(features.reshape(-1, 2) - backward.reshape(-1, 2), axis=1)
    valid &= fb_error <= 1.5
    vectors = forward.reshape(-1, 2)[valid] - features.reshape(-1, 2)[valid]
    if len(vectors):
        magnitudes = np.linalg.norm(vectors, axis=1)
        median = np.median(magnitudes); mad = np.median(np.abs(magnitudes - median))
        limit = median + max(3 * 1.4826 * mad, 1.0)
        vectors = vectors[magnitudes <= limit]
    metrics = {"features_detected": detected, **robust_track_metrics(vectors, dt_seconds)}
    metrics["quality"] = min(1.0, metrics["tracks_valid"] / max(30, detected))
    return metrics, vectors


def farneback_pair(previous: np.ndarray, current: np.ndarray, dt_seconds: float, mask=None) -> dict:
    started = time.perf_counter()
    flow = cv2.calcOpticalFlowFarneback(previous, current, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    elapsed_ms = (time.perf_counter() - started) * 1000
    values = flow[mask > 0] if mask is not None else flow.reshape(-1, 2)
    magnitudes = np.linalg.norm(values, axis=1)
    return {
        "farneback_motion_score": float(np.median(magnitudes)) / max(dt_seconds, 1e-6),
        "farneback_p90": float(np.percentile(magnitudes, 90)),
        "farneback_cpu_ms": elapsed_ms,
    }


def dominant_axis(vector_groups: Iterable[np.ndarray]) -> np.ndarray:
    vectors = np.concatenate([group for group in vector_groups if len(group)], axis=0)
    if len(vectors) < 2:
        return np.array([1.0, 0.0])
    covariance = np.cov(vectors.T)
    axis = np.linalg.eigh(covariance)[1][:, -1]
    if float(np.median(vectors @ axis)) < 0:
        axis = -axis
    return axis / np.linalg.norm(axis)


def choose_thresholds(rows: list[dict], markers: dict[str, int], field="projected_motion_score") -> tuple[float, float]:
    stopped = [float(row[field]) for row in rows if markers["STOPPED"] <= row["timestamp_ns"] <= markers["RESUMED"]]
    moving = [float(row[field]) for row in rows if row["timestamp_ns"] < markers["STOPPED"] or row["timestamp_ns"] > markers["RESUMED"]]
    if not stopped or not moving:
        raise ValueError("not enough marked STOPPED/MOVING samples for candidate thresholds")
    stopped_p90 = float(np.percentile(stopped, 90)); moving_p25 = float(np.percentile(moving, 25))
    stop = max(0.0, (stopped_p90 + moving_p25) / 2)
    start = max(stop * 1.5, (float(np.percentile(stopped, 95)) + float(np.percentile(moving, 40))) / 2)
    return stop, start


@dataclass
class MotionFSM:
    stop_threshold: float
    start_threshold: float
    stop_confirm_ms: float = 750
    move_confirm_ms: float = 500
    minimum_valid_tracks: int = 8
    state: str = "UNKNOWN"
    candidate_since_ns: int | None = None

    def update(self, timestamp_ns: int, score: float, valid_tracks: int) -> str:
        if valid_tracks < self.minimum_valid_tracks:
            self.state = "UNKNOWN"; self.candidate_since_ns = None; return self.state
        if self.state in {"UNKNOWN", "MOVING", "MOVE_CANDIDATE"}:
            if score <= self.stop_threshold:
                if self.state != "STOP_CANDIDATE": self.state = "STOP_CANDIDATE"; self.candidate_since_ns = timestamp_ns
                if (timestamp_ns - self.candidate_since_ns) / 1e6 >= self.stop_confirm_ms: self.state = "STOPPED"
            elif self.state == "UNKNOWN" or score >= self.start_threshold:
                self.state = "MOVING"; self.candidate_since_ns = None
        elif self.state in {"STOPPED", "STOP_CANDIDATE"}:
            if score >= self.start_threshold:
                if self.state != "MOVE_CANDIDATE": self.state = "MOVE_CANDIDATE"; self.candidate_since_ns = timestamp_ns
                if (timestamp_ns - self.candidate_since_ns) / 1e6 >= self.move_confirm_ms: self.state = "MOVING"
            elif score <= self.stop_threshold:
                if self.state == "STOP_CANDIDATE" and (timestamp_ns - self.candidate_since_ns) / 1e6 >= self.stop_confirm_ms: self.state = "STOPPED"
                elif self.state == "MOVE_CANDIDATE": self.state = "STOPPED"; self.candidate_since_ns = None
        return self.state


def lidar_similarity(previous: dict, current: dict) -> dict[str, float | int | None]:
    left = previous["ranges_mm"]; right = current["ranges_mm"]
    if len(left) != len(right):
        raise ValueError("LiDAR beam counts differ")
    pairs = [(float(a), float(b)) for a, b in zip(left, right) if a is not None and b is not None]
    if not pairs:
        return {"common_valid_beams": 0, "median_abs_difference_mm": None, "rmse_mm": None, "correlation": None}
    a = np.array([pair[0] for pair in pairs]); b = np.array([pair[1] for pair in pairs]); delta = a - b
    correlation = float(np.corrcoef(a, b)[0, 1]) if len(a) > 1 and np.std(a) and np.std(b) else None
    return {
        "common_valid_beams": len(pairs),
        "median_abs_difference_mm": float(np.median(np.abs(delta))),
        "rmse_mm": float(np.sqrt(np.mean(delta * delta))),
        "correlation": correlation,
    }


def fusion_rule(camera_state: str, camera_quality: float, lidar_state: str) -> tuple[str, float]:
    camera_known = camera_state in {"MOVING", "STOPPED"} and camera_quality >= 0.3
    lidar_known = lidar_state in {"MOVING", "STOPPED"}
    if camera_known and lidar_known and camera_state == lidar_state: return camera_state, min(1.0, 0.5 + camera_quality / 2)
    if camera_known and not lidar_known: return camera_state, camera_quality * 0.7
    if lidar_known and not camera_known: return lidar_state, 0.5
    return "UNKNOWN", 0.0


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(dict.fromkeys(key for row in rows for key in row)) or ["empty"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore"); writer.writeheader(); writer.writerows(rows)


def draw_plot(path: Path, camera: list[dict], lidar: list[dict], markers: dict[str, int]) -> None:
    width, height, margin = 1600, 700, 70
    image = np.full((height, width, 3), 255, dtype=np.uint8)
    times = [row["timestamp_ns"] for row in camera] + [row["timestamp_ns"] for row in lidar]
    if not times: return
    start, end = min(times), max(times); span = max(end - start, 1)
    x = lambda value: margin + round((value - start) / span * (width - 2 * margin))
    for label, color in (("STOPPED", (0, 0, 255)), ("RESUMED", (0, 150, 0))):
        position = x(markers[label]); cv2.line(image, (position, margin), (position, height-margin), color, 2); cv2.putText(image, label, (position+5, margin+20), 0, .6, color, 2)
    def line(rows, field, color):
        values = [float(row[field]) for row in rows if row.get(field) is not None]
        scale = max(float(np.percentile(values, 95)) if values else 1, 1e-6)
        points = [(x(row["timestamp_ns"]), height-margin-round(min(float(row[field])/scale, 1.2)*(height-2*margin)/1.2)) for row in rows if row.get(field) is not None]
        for first, second in zip(points, points[1:]): cv2.line(image, first, second, color, 2)
    line(camera, "projected_motion_score", (255, 0, 0)); line(lidar, "median_abs_difference_mm", (0, 140, 255))
    cv2.imwrite(str(path), image)


def analyze(session_dir: Path, output: Path, roi_polygon=None, verify_hashes=True, run_farneback=True) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((session_dir / "manifest.json").read_text(encoding="utf-8"))
    markers = parse_markers(session_dir / "markers.jsonl")
    frames = load_frame_rows(session_dir, verify_hashes)
    camera_rows, vectors_by_row = [], []
    previous = None
    for frame in frames:
        image = cv2.imread(frame["path"], cv2.IMREAD_GRAYSCALE)
        if image is None: raise ValueError(f"cannot decode {frame['path']}")
        if previous is not None:
            dt = (frame["captured_monotonic_ns"] - previous[0]) / 1e9
            mask = normalized_polygon_mask(image.shape, roi_polygon)
            started = time.perf_counter(); metrics, vectors = lk_pair(previous[1], image, dt, mask); lk_ms = (time.perf_counter()-started)*1000
            farneback = farneback_pair(previous[1], image, dt, mask) if run_farneback else {}
            row = {"timestamp_ns": frame["captured_monotonic_ns"], "captured_utc": frame.get("captured_utc"), "dt_ms": dt*1000, **metrics, "lk_cpu_ms": lk_ms, **farneback}
            camera_rows.append(row); vectors_by_row.append(vectors)
        previous = (frame["captured_monotonic_ns"], image)
    moving_vectors = [vectors for row, vectors in zip(camera_rows, vectors_by_row) if row["timestamp_ns"] < markers["STOPPED"] or row["timestamp_ns"] > markers["RESUMED"]]
    axis = dominant_axis(moving_vectors)
    for row, vectors in zip(camera_rows, vectors_by_row):
        projections = vectors @ axis if len(vectors) else np.array([])
        row["projected_signed_px"] = float(np.median(projections)) if len(projections) else 0.0
        row["projected_motion_score"] = float(np.median(np.abs(projections))) / max(row["dt_ms"]/1000, 1e-6) if len(projections) else 0.0
    stop_threshold, start_threshold = choose_thresholds(camera_rows, markers)
    fsm = MotionFSM(stop_threshold, start_threshold)
    for row in camera_rows: row["detected_state"] = fsm.update(row["timestamp_ns"], row["projected_motion_score"], row["tracks_valid"])

    lidar_profiles = read_jsonl(session_dir / "lidar" / "raw_scans.jsonl")
    lidar_profiles.sort(key=lambda row: int(row["captured_monotonic_ns"]))
    lidar_rows = []
    for previous_lidar, current_lidar in zip(lidar_profiles, lidar_profiles[1:]):
        lidar_rows.append({"timestamp_ns": int(current_lidar["captured_monotonic_ns"]), **lidar_similarity(previous_lidar, current_lidar)})
    lidar_stop, lidar_start = choose_thresholds(lidar_rows, markers, "median_abs_difference_mm")
    for row in lidar_rows:
        score = row["median_abs_difference_mm"]
        row["detected_state"] = "UNKNOWN" if score is None else "STOPPED" if score <= lidar_stop else "MOVING" if score >= lidar_start else "UNKNOWN"

    fusion_rows = []
    for camera_row in camera_rows:
        nearest = min(lidar_rows, key=lambda row: abs(row["timestamp_ns"]-camera_row["timestamp_ns"])) if lidar_rows else None
        state, confidence = fusion_rule(camera_row["detected_state"], camera_row["quality"], nearest["detected_state"] if nearest else "UNKNOWN")
        fusion_rows.append({"timestamp_ns": camera_row["timestamp_ns"], "camera_state": camera_row["detected_state"], "lidar_state": nearest["detected_state"] if nearest else "UNKNOWN", "fused_state": state, "confidence": confidence})

    def first_state(rows, state, after):
        return next((row["timestamp_ns"] for row in rows if row["timestamp_ns"] >= after and row["detected_state"] == state), None)
    detected_stop = first_state(camera_rows, "STOPPED", markers["STOPPED"]); detected_resume = first_state(camera_rows, "MOVING", markers["RESUMED"])
    profiles_during = sum(markers["STOPPED"] <= int(row["captured_monotonic_ns"]) <= markers["RESUMED"] for row in lidar_profiles)
    events_count = len(read_jsonl(session_dir / "events.jsonl")); markers_count = len(read_jsonl(session_dir / "markers.jsonl"))
    false_stop_ms = sum(row["dt_ms"] for row in camera_rows if row["detected_state"] == "STOPPED" and not (markers["STOPPED"] <= row["timestamp_ns"] <= markers["RESUMED"]))
    false_moving_ms = sum(row["dt_ms"] for row in camera_rows if row["detected_state"] == "MOVING" and markers["STOPPED"] <= row["timestamp_ns"] <= markers["RESUMED"])
    unknown_ms = sum(row["dt_ms"] for row in camera_rows if row["detected_state"] == "UNKNOWN")
    def distribution(rows, field, stopped):
        values = [float(row[field]) for row in rows if row.get(field) is not None and ((markers["STOPPED"] <= row["timestamp_ns"] <= markers["RESUMED"]) == stopped)]
        return {"count": len(values), "median": statistics.median(values) if values else None, "p90": float(np.percentile(values, 90)) if values else None}
    summary = {
        "dataset_is_real": True,
        "session_key": manifest.get("session_key"),
        "manual_stop_monotonic_ns": markers["STOPPED"], "manual_resume_monotonic_ns": markers["RESUMED"],
        "manual_stop_duration_sec": (markers["RESUMED"]-markers["STOPPED"])/1e9,
        "camera_frames_verified": len(frames), "dominant_axis_xy": axis.tolist(),
        "threshold_candidates": {"camera_stop": stop_threshold, "camera_start": start_threshold, "lidar_stop": lidar_stop, "lidar_start": lidar_start},
        "detected_stop_monotonic_ns": detected_stop, "stop_detection_delay_ms": (detected_stop-markers["STOPPED"])/1e6 if detected_stop else None,
        "detected_resume_monotonic_ns": detected_resume, "resume_detection_delay_ms": (detected_resume-markers["RESUMED"])/1e6 if detected_resume else None,
        "quality": {"false_stop_duration_ms": false_stop_ms, "false_moving_duration_ms": false_moving_ms, "unknown_duration_ms": unknown_ms},
        "camera_score_distributions": {"moving": distribution(camera_rows, "projected_motion_score", False), "stopped": distribution(camera_rows, "projected_motion_score", True)},
        "lidar_difference_distributions": {"moving": distribution(lidar_rows, "median_abs_difference_mm", False), "stopped": distribution(lidar_rows, "median_abs_difference_mm", True)},
        "farneback_comparator": {
            "enabled": run_farneback,
            "lk_cpu_ms_median": statistics.median(row["lk_cpu_ms"] for row in camera_rows) if camera_rows else None,
            "farneback_cpu_ms_median": statistics.median(row["farneback_cpu_ms"] for row in camera_rows) if run_farneback and camera_rows else None,
            "moving_score": distribution(camera_rows, "farneback_motion_score", False) if run_farneback else None,
            "stopped_score": distribution(camera_rows, "farneback_motion_score", True) if run_farneback else None,
        },
        "lidar_profiles": {"total": len(lidar_profiles), "before_stop": sum(int(row["captured_monotonic_ns"]) < markers["STOPPED"] for row in lidar_profiles), "during_stop": profiles_during, "after_resume": sum(int(row["captured_monotonic_ns"]) > markers["RESUMED"] for row in lidar_profiles)},
        "event_accounting": {"events_jsonl": events_count, "markers_jsonl": markers_count, "combined_analyzer_timeline": events_count + markers_count, "manifest_events": manifest.get("record_counts", {}).get("events"), "explanation": "The base analyzer combines events.jsonl and markers.jsonl; markers remain separately counted in the manifest."},
        "conclusion": "Run on the real dataset and inspect delays/errors before choosing YES/CONDITIONALLY/NO.",
    }
    write_csv(output / "camera_motion.csv", camera_rows); write_csv(output / "lidar_motion.csv", lidar_rows); write_csv(output / "fusion_motion.csv", fusion_rows)
    draw_plot(output / "motion_plot.png", camera_rows, lidar_rows, markers)
    (output / "motion_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir", type=Path); parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--roi", type=Path, help="JSON normalized polygon [[x,y], ...]")
    parser.add_argument("--no-verify-hashes", action="store_true")
    parser.add_argument("--skip-farneback", action="store_true")
    args = parser.parse_args(); output = args.output_dir or args.session_dir / "motion_analysis"
    polygon = json.loads(args.roi.read_text(encoding="utf-8")) if args.roi else None
    print(json.dumps(analyze(args.session_dir, output, polygon, not args.no_verify_hashes, not args.skip_farneback), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__": raise SystemExit(main())
