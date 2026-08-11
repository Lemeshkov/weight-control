"""Cross-session offline research of camera motion metrics.

All supplied sessions are DEVELOPMENT data. Candidate selection is pooled across
sessions; no per-session threshold is produced.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

try:
    from scripts.analyze_camera_motion import load_frame_rows, read_jsonl, write_csv
    from scripts.validate_camera_motion import FrozenFarnebackCandidate, duration_metrics, fixed_hysteresis, parse_ground_truth, simulate_profiles
except ModuleNotFoundError:
    from analyze_camera_motion import load_frame_rows, read_jsonl, write_csv
    from validate_camera_motion import FrozenFarnebackCandidate, duration_metrics, fixed_hysteresis, parse_ground_truth, simulate_profiles


SCENARIOS = {
    "9fafd185315e4b8194d7b59b5afb6f39": "stop-resume",
    "c65c0b53513d4c64a43d7469a7d1bc73": "stop-resume",
    "0700fa3a0c254fdf9edbed8f13acab07": "no-stop",
}
DEVELOPMENT_ROLE = {
    "9fafd185315e4b8194d7b59b5afb6f39": "TUNING",
    "c65c0b53513d4c64a43d7469a7d1bc73": "DEVELOPMENT_FORMER_VALIDATION",
    "0700fa3a0c254fdf9edbed8f13acab07": "DEVELOPMENT_FORMER_VALIDATION",
}
ANALYSIS_WIDTH = 256
GRADIENT_THRESHOLD = 0.04
PIXEL_NOISE_FLOOR_PX_PER_SEC = 0.15
TILE_ROWS, TILE_COLUMNS = 4, 8
BACKGROUND_REFERENCE_FRAMES = 10
FOREGROUND_DIFFERENCE_THRESHOLD = 0.08


def marker_truth(session: Path, scenario: str) -> dict[str, int]:
    found, issues = parse_ground_truth(session / "markers.jsonl", scenario)
    if issues: raise ValueError(f"incomplete markers: {session}: {issues}")
    return found


def ground_truth(timestamp: int, scenario: str, markers: dict[str, int]) -> str:
    if timestamp < markers["VEHICLE_ENTERED"] or timestamp >= markers["VEHICLE_EXITED"]: return "NO_VEHICLE"
    if scenario == "no-stop": return "MOVING"
    return "STOPPED" if markers["STOPPED"] <= timestamp < markers["RESUMED"] else "MOVING"


def image_metrics(gray: np.ndarray) -> tuple[dict[str, float], np.ndarray]:
    normalized = gray.astype(np.float32) / 255.0
    gx = cv2.Sobel(normalized, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(normalized, cv2.CV_32F, 0, 1, ksize=3)
    gradient = cv2.magnitude(gx, gy)
    return {"brightness": float(np.mean(normalized)), "contrast": float(np.std(normalized)),
            "gradient_energy": float(np.mean(gradient)),
            "informative_pixel_ratio": float(np.mean(gradient >= GRADIENT_THRESHOLD))}, gradient


def flow_metrics(previous: np.ndarray, current: np.ndarray, dt_seconds: float, gradient: np.ndarray) -> dict[str, float]:
    started = time.perf_counter()
    flow = cv2.calcOpticalFlowFarneback(previous, current, None, .5, 3, 15, 3, 5, 1.2, 0)
    cpu_ms = (time.perf_counter() - started) * 1000
    magnitude = cv2.magnitude(flow[..., 0], flow[..., 1]) / max(dt_seconds, 1e-6)
    informative = gradient >= GRADIENT_THRESHOLD
    values = magnitude[informative]
    if not len(values): values = magnitude.ravel()
    spatial_noise = float(np.percentile(values, 20))
    adaptive_floor = max(PIXEL_NOISE_FLOOR_PX_PER_SEC, 4 * spatial_noise)
    tile_values = []
    height, width = magnitude.shape
    for row in range(TILE_ROWS):
        for column in range(TILE_COLUMNS):
            ys = slice(row * height // TILE_ROWS, (row + 1) * height // TILE_ROWS)
            xs = slice(column * width // TILE_COLUMNS, (column + 1) * width // TILE_COLUMNS)
            mask = informative[ys, xs]
            tile = magnitude[ys, xs][mask]
            if len(tile) >= 20: tile_values.append(float(np.percentile(tile, 75)))
    tile_array = np.asarray(tile_values or [0.0])
    difference = cv2.absdiff(previous, current).astype(np.float32) / 255.0
    changed = difference >= (5 / 255)
    ys, xs = np.where(changed)
    if len(xs):
        bbox_area = ((xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1)) / (width * height)
        centroid_x, centroid_y = float(np.mean(xs) / width), float(np.mean(ys) / height)
        edge_fraction = float(np.mean((xs < .1 * width) | (xs > .9 * width)))
    else: bbox_area = centroid_x = centroid_y = edge_fraction = 0.0
    informative_p75 = float(np.percentile(values, 75))
    gradient_mean = float(np.mean(gradient[informative])) if np.any(informative) else 0.0
    return {
        "raw_flow_median": float(np.median(magnitude)),
        "informative_flow_median": float(np.median(values)),
        "informative_flow_p75": informative_p75,
        "informative_flow_p90": float(np.percentile(values, 90)),
        "normalized_flow_p75": informative_p75 / max(gradient_mean, .02),
        "active_pixel_ratio": float(np.mean(values > PIXEL_NOISE_FLOOR_PX_PER_SEC)),
        "adaptive_noise_floor": adaptive_floor,
        "adaptive_active_pixel_ratio": float(np.mean(values > adaptive_floor)),
        "tile_flow_median": float(np.median(tile_array)),
        "tile_flow_p75": float(np.percentile(tile_array, 75)),
        "active_tile_ratio": float(np.mean(tile_array > PIXEL_NOISE_FLOOR_PX_PER_SEC)),
        "changed_pixel_ratio": float(np.mean(changed)), "motion_bbox_area": float(bbox_area),
        "motion_centroid_x": centroid_x, "motion_centroid_y": centroid_y,
        "motion_edge_fraction": edge_fraction, "farneback_cpu_ms": cpu_ms,
    }


def foreground_metrics(image: np.ndarray, background: np.ndarray) -> dict[str, float | bool]:
    difference = cv2.absdiff(image, background).astype(np.float32) / 255.0
    mask = (difference >= FOREGROUND_DIFFERENCE_THRESHOLD).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    height, width = image.shape
    if not contours:
        return {"foreground_area_ratio": 0.0, "foreground_bbox_area": 0.0,
                "foreground_centroid_x": 0.0, "foreground_centroid_y": 0.0,
                "foreground_touches_edge": False}
    contour = max(contours, key=cv2.contourArea); x, y, w, h = cv2.boundingRect(contour)
    moments = cv2.moments(contour)
    cx = moments["m10"] / moments["m00"] if moments["m00"] else x + w / 2
    cy = moments["m01"] / moments["m00"] if moments["m00"] else y + h / 2
    return {"foreground_area_ratio": float(cv2.contourArea(contour) / (width * height)),
            "foreground_bbox_area": float(w * h / (width * height)),
            "foreground_centroid_x": float(cx / width), "foreground_centroid_y": float(cy / height),
            "foreground_touches_edge": bool(x == 0 or y == 0 or x + w == width or y + h == height)}


def augment_presence_from_frames(root: Path, rows: list[dict[str, Any]]) -> None:
    by_key = {key: [row for row in rows if row["session_key"] == key] for key in SCENARIOS}
    for key, selected in by_key.items():
        frames = load_frame_rows(root / key, verify_hashes=False)
        decoded = []
        for frame in frames:
            image = cv2.imread(frame["path"], cv2.IMREAD_GRAYSCALE)
            height = round(image.shape[0] * ANALYSIS_WIDTH / image.shape[1])
            decoded.append(cv2.resize(image, (ANALYSIS_WIDTH, height), interpolation=cv2.INTER_AREA))
        background = np.median(np.stack(decoded[:BACKGROUND_REFERENCE_FRAMES]), axis=0).astype(np.uint8)
        lookup = {int(row["timestamp_ns"]): row for row in selected}
        for frame, image in zip(frames, decoded):
            timestamp = int(frame["captured_monotonic_ns"])
            if timestamp in lookup: lookup[timestamp].update(foreground_metrics(image, background))


def extract_session(session: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    key, scenario = session.name, SCENARIOS[session.name]
    markers = marker_truth(session, scenario)
    frames = load_frame_rows(session, verify_hashes=True)
    old_scores = {}
    old_path = session / "motion_validation" / "camera_validation.csv"
    if old_path.is_file():
        with old_path.open(encoding="utf-8", newline="") as handle:
            old_scores = {int(row["timestamp_ns"]): float(row["motion_score"]) for row in csv.DictReader(handle)}
    rows, previous = [], None
    for frame in frames:
        image = cv2.imread(frame["path"], cv2.IMREAD_GRAYSCALE)
        if image is None: raise ValueError(frame["path"])
        height = round(image.shape[0] * ANALYSIS_WIDTH / image.shape[1])
        image = cv2.resize(image, (ANALYSIS_WIDTH, height), interpolation=cv2.INTER_AREA)
        appearance, gradient = image_metrics(image)
        timestamp = int(frame["captured_monotonic_ns"])
        if previous is not None:
            dt = (timestamp - previous[0]) / 1e9
            rows.append({"session_key": key, "dataset_role": DEVELOPMENT_ROLE[key], "scenario": scenario,
                         "timestamp_ns": timestamp, "ground_truth_state": ground_truth(timestamp, scenario, markers),
                         "frame_interval_ms": dt * 1000, "rtsp_long_interval": dt > .5,
                         "old_absolute_score": old_scores.get(timestamp), **appearance,
                         **flow_metrics(previous[1], image, dt, gradient)})
        previous = (timestamp, image)
    return rows, {"session_key": key, "dataset_role": DEVELOPMENT_ROLE[key], "scenario": scenario,
                  "camera_frames": len(frames), "score_rows": len(rows), "markers": markers}


SCORE_FIELDS = ["old_absolute_score", "raw_flow_median", "informative_flow_median", "informative_flow_p75",
                "informative_flow_p90", "normalized_flow_p75", "active_pixel_ratio",
                "adaptive_active_pixel_ratio", "tile_flow_median", "tile_flow_p75", "active_tile_ratio"]


def distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values: return {"count": 0, "median": None, "p10": None, "p90": None}
    return {"count": len(values), "median": float(np.median(values)),
            "p10": float(np.percentile(values, 10)), "p90": float(np.percentile(values, 90))}


def candidate_is_ready(candidate: dict[str, Any], session_count: int) -> bool:
    return candidate["sessions_basic_pass"] == session_count and candidate["false_transitions"] == 0


def candidate_search(rows: list[dict[str, Any]], sessions: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    by_session = {key: [row for row in rows if row["session_key"] == key] for key in sessions}
    for field in SCORE_FIELDS[1:]:
        pooled = np.asarray([float(row[field]) for row in rows if row["ground_truth_state"] in {"MOVING", "STOPPED"}])
        for stop in sorted(set(float(x) for x in np.percentile(pooled, [2, 5, 10, 15, 20, 25, 30, 35]))):
            for start in sorted(set(float(x) for x in np.percentile(pooled, [20, 30, 40, 50, 60, 70]))):
                if start <= stop: continue
                for stop_ms in (1000, 1500, 2000, 2500):
                    for resume_ms in (500, 750, 1000):
                        total_false_stop = total_false_moving = total_delay = 0.0
                        false_transitions = 0; passed = 0
                        for key, meta in sessions.items():
                            subset = [dict(row, motion_score=row[field]) for row in by_session[key]]
                            candidate = FrozenFarnebackCandidate("cross-session metric", stop, start, stop_ms, resume_ms)
                            timeline = fixed_hysteresis(subset, candidate)
                            metrics = duration_metrics(timeline, meta["scenario"], meta["markers"])
                            total_false_stop += metrics["false_stop_duration_ms"]
                            total_false_moving += metrics["false_moving_duration_ms"]
                            false_transitions += metrics.get("false_stop_transitions", 0) + metrics.get("false_resume_transitions", 0)
                            if meta["scenario"] == "stop-resume":
                                delays = (metrics.get("stop_detection_delay_ms"), metrics.get("resume_detection_delay_ms"))
                                total_delay += sum(100_000 if value is None else value for value in delays)
                            session_ok = metrics["false_stop_duration_ms"] == 0 if meta["scenario"] == "no-stop" else (
                                metrics.get("stop_detection_delay_ms") is not None and metrics.get("resume_detection_delay_ms") is not None)
                            passed += bool(session_ok and metrics.get("false_stop_transitions", 0) == 0)
                        objective = 20 * total_false_stop + 4 * total_false_moving + total_delay + 20_000 * false_transitions
                        results.append({"score_field": field, "stop_threshold": stop, "start_threshold": start,
                                        "stop_confirmation_ms": stop_ms, "resume_confirmation_ms": resume_ms,
                                        "development_objective": objective, "false_stop_ms": total_false_stop,
                                        "false_moving_ms": total_false_moving, "false_transitions": false_transitions,
                                        "sessions_basic_pass": passed})
    return sorted(results, key=lambda row: (row["development_objective"], -row["sessions_basic_pass"]))


def draw_distributions(path: Path, rows: list[dict[str, Any]], _field: str | None = None) -> None:
    """Draw cross-session state medians for representative metric families."""
    width, height, margin = 1500, 900, 80
    image = np.full((height, width, 3), 255, np.uint8)
    fields = ["old_absolute_score", "informative_flow_p75", "active_pixel_ratio", "tile_flow_p75"]
    keys = list(SCENARIOS)
    colors = [(220, 80, 30), (30, 150, 30), (30, 30, 220)]
    panel_width = (width - 2 * margin) // len(fields)
    for panel, field in enumerate(fields):
        left = margin + panel * panel_width
        values = [float(row[field]) for row in rows if row.get(field) is not None]
        maximum = max(float(np.percentile(values, 95)), 1e-9)
        cv2.putText(image, field, (left, 45), 0, .48, (0, 0, 0), 1)
        for index, (key, color) in enumerate(zip(keys, colors)):
            moving = [float(x[field]) for x in rows if x.get(field) is not None and x["session_key"] == key and x["ground_truth_state"] == "MOVING"]
            stopped = [float(x[field]) for x in rows if x.get(field) is not None and x["session_key"] == key and x["ground_truth_state"] == "STOPPED"]
            base_y = 150 + index * 230
            cv2.putText(image, key[:8], (left, base_y-35), 0, .46, color, 1)
            for label, sample, y in (("M", moving, base_y), ("S", stopped, base_y+65)):
                cv2.putText(image, label, (left, y+15), 0, .5, color, 1)
                if sample:
                    length = round(min(float(np.median(sample)) / maximum, 1.0) * (panel_width-55))
                    cv2.rectangle(image, (left+25, y), (left+25+length, y+20), color, -1)
                    cv2.putText(image, f"{np.median(sample):.3g}", (left+25, y+42), 0, .4, (50,50,50), 1)
        cv2.line(image, (left, 65), (left, height-45), (210,210,210), 1)
    cv2.putText(image, "Bars are per-session medians; M=MOVING, S=STOPPED; each panel uses its own pooled p95 scale",
                (margin, height-20), 0, .5, (50,50,50), 1)
    cv2.imwrite(str(path), image)


def draw_session_comparison(path: Path, summaries: list[dict[str, Any]]) -> None:
    image = np.full((700, 1500, 3), 255, np.uint8)
    fields = ["brightness", "contrast", "gradient_energy", "changed_pixel_ratio", "frame_interval_ms", "motion_bbox_area"]
    for row_index, summary in enumerate(summaries):
        cv2.putText(image, summary["session_key"][:8], (30, 90+row_index*180), 0, .65, (0,0,0), 2)
        for column, field in enumerate(fields):
            value = summary["appearance_and_capture"][field]["median"]
            cv2.putText(image, f"{field[:12]}={value:.4g}", (190+column*210, 90+row_index*180), 0, .45, (30,30,30), 1)
    cv2.imwrite(str(path), image)


def research(root: Path, output: Path, reuse_scores: bool = False) -> dict[str, Any]:
    all_rows, session_meta, summaries = [], {}, []
    for key in SCENARIOS:
        if reuse_scores:
            meta = {"session_key": key, "dataset_role": DEVELOPMENT_ROLE[key], "scenario": SCENARIOS[key],
                    "camera_frames": sum(1 for _ in csv.DictReader((root / key / "camera" / "frames.csv").open(encoding="utf-8"))),
                    "markers": marker_truth(root / key, SCENARIOS[key])}
        else:
            rows, meta = extract_session(root / key); all_rows.extend(rows)
        session_meta[key] = meta
    if reuse_scores:
        with (output / "cross_session_scores.csv").open(encoding="utf-8", newline="") as handle:
            all_rows = list(csv.DictReader(handle))
        for row in all_rows:
            for field in SCORE_FIELDS + ["brightness", "contrast", "gradient_energy", "informative_pixel_ratio",
                                         "changed_pixel_ratio", "frame_interval_ms", "motion_bbox_area",
                                         "motion_centroid_x", "motion_edge_fraction", "farneback_cpu_ms"]:
                if row.get(field) not in (None, ""): row[field] = float(row[field])
            row["timestamp_ns"] = int(row["timestamp_ns"])
            row["rtsp_long_interval"] = str(row["rtsp_long_interval"]).lower() == "true"
    if not all("foreground_area_ratio" in row for row in all_rows):
        augment_presence_from_frames(root, all_rows)
    for key, meta in session_meta.items():
        selected = [row for row in all_rows if row["session_key"] == key]
        score_summary = {field: {state.lower(): distribution([float(row[field]) for row in selected if row[field] is not None and row["ground_truth_state"] == state]) for state in ("MOVING", "STOPPED")} for field in SCORE_FIELDS}
        appearance = {field: distribution([float(row[field]) for row in selected]) for field in
                      ("brightness", "contrast", "gradient_energy", "informative_pixel_ratio", "changed_pixel_ratio", "frame_interval_ms", "motion_bbox_area", "motion_centroid_x", "motion_edge_fraction", "farneback_cpu_ms")}
        presence = {field: distribution([float(row[field]) for row in selected]) for field in
                    ("foreground_area_ratio", "foreground_bbox_area", "foreground_centroid_x", "foreground_centroid_y")}
        summaries.append({**meta, "score_distributions": score_summary, "appearance_and_capture": appearance,
                          "background_reference_presence": presence,
                          "foreground_edge_frames": sum(bool(row["foreground_touches_edge"]) for row in selected),
                          "rtsp_long_intervals_over_500ms": sum(row["rtsp_long_interval"] for row in selected),
                          "partial_exit_candidates": sum(row["motion_bbox_area"] < .05 or row["motion_edge_fraction"] > .5 for row in selected)})
    search = candidate_search(all_rows, session_meta); best = search[0]
    best_by_metric = {field: next(item for item in search if item["score_field"] == field) for field in SCORE_FIELDS[1:]}
    candidate_ready = candidate_is_ready(best, len(session_meta))
    per_session = []
    for key, meta in session_meta.items():
        subset = [dict(row, motion_score=row[best["score_field"]]) for row in all_rows if row["session_key"] == key]
        candidate = FrozenFarnebackCandidate("v2 " + best["score_field"], best["stop_threshold"], best["start_threshold"], best["stop_confirmation_ms"], best["resume_confirmation_ms"])
        timeline = fixed_hysteresis(subset, candidate); metrics = duration_metrics(timeline, meta["scenario"], meta["markers"])
        profiles = read_jsonl(root / key / "lidar" / "raw_scans.jsonl")
        _, slices = simulate_profiles(profiles, timeline, meta["scenario"], meta["markers"])
        per_session.append({"session_key": key, "scenario": meta["scenario"], "metrics": metrics, "slice_simulation": slices})
    output.mkdir(parents=True, exist_ok=True); write_csv(output / "cross_session_scores.csv", all_rows)
    report = {"dataset_policy": "all three sessions are DEVELOPMENT; none is an independent validation",
              "old_candidate_result": "REJECTED", "feature_constants": {"analysis_width": ANALYSIS_WIDTH,
              "gradient_threshold": GRADIENT_THRESHOLD, "pixel_noise_floor_px_per_sec": PIXEL_NOISE_FLOOR_PX_PER_SEC,
              "tile_grid": [TILE_ROWS, TILE_COLUMNS], "background_reference_frames": BACKGROUND_REFERENCE_FRAMES,
              "foreground_difference_threshold": FOREGROUND_DIFFERENCE_THRESHOLD}, "sessions": summaries,
              "pooled_development_search_count": len(search), "best_attempt_by_metric": best_by_metric,
              "best_development_attempt": best, "candidate_status": "READY_FOR_VALIDATION" if candidate_ready else "NOT_READY",
              "recommended_candidate": best if candidate_ready else None,
              "blocking_finding": "Ground truth labels long empty/static intervals as MOVING; motion and presence are not identifiable from one motion score.",
              "best_attempt_per_session": per_session}
    (output / "cross_session_summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    draw_distributions(output / "score_distributions.png", all_rows, best["score_field"])
    draw_session_comparison(output / "session_comparison.png", summaries)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("diagnostics_root", type=Path)
    parser.add_argument("--output-dir", type=Path); parser.add_argument("--reuse-scores", action="store_true"); args = parser.parse_args()
    output = args.output_dir or args.diagnostics_root / "motion_metric_research"
    report = research(args.diagnostics_root.resolve(), output.resolve(), args.reuse_scores)
    print(json.dumps({"old_candidate": report["old_candidate_result"], "candidate_status": report["candidate_status"],
                      "recommended_candidate": report["recommended_candidate"], "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__": main()
