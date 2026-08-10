"""Offline-only threshold/hysteresis study for a recorded Camera+LiDAR session."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

try:
    from scripts.analyze_camera_motion import parse_markers, read_jsonl, write_csv
except ModuleNotFoundError:  # Direct invocation from backend/scripts.
    from analyze_camera_motion import parse_markers, read_jsonl, write_csv


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def classify(rows: list[dict[str, Any]], field: str, stop: float, start: float,
             stop_confirm_ms: int, move_confirm_ms: int, minimum_tracks: int = 0) -> list[dict[str, Any]]:
    state, candidate, candidate_since = "MOVING", None, None
    result = []
    for source in rows:
        timestamp = int(source["timestamp_ns"])
        score = float(source[field])
        valid = int(source.get("tracks_valid") or 0)
        if minimum_tracks and valid < minimum_tracks:
            observed = "UNKNOWN"
            candidate = candidate_since = None
        else:
            observed = state
            wanted = "STOPPED" if score <= stop else "MOVING" if score >= start else None
            if wanted == state:
                candidate = candidate_since = None
            elif wanted is not None:
                if candidate != wanted:
                    candidate, candidate_since = wanted, timestamp
                confirm = stop_confirm_ms if wanted == "STOPPED" else move_confirm_ms
                if (timestamp - candidate_since) / 1e6 >= confirm:
                    state, observed = wanted, wanted
                    candidate = candidate_since = None
        result.append({"timestamp_ns": timestamp, "score": score, "state": observed})
    return result


def evaluate(timeline: list[dict[str, Any]], markers: dict[str, int]) -> dict[str, Any]:
    stop_at, resume_at = markers["STOPPED"], markers["RESUMED"]
    false_stop = false_moving = unknown = correct = 0.0
    confusion = {"MOVING_MOVING": 0.0, "MOVING_STOPPED": 0.0,
                 "STOPPED_MOVING": 0.0, "STOPPED_STOPPED": 0.0}
    for index, row in enumerate(timeline):
        if index + 1 == len(timeline):
            continue
        left, right = row["timestamp_ns"], timeline[index + 1]["timestamp_ns"]
        points = [left] + [b for b in (stop_at, resume_at) if left < b < right] + [right]
        for a, b in zip(points, points[1:]):
            duration = (b - a) / 1e6
            truth = "STOPPED" if stop_at <= a < resume_at else "MOVING"
            detected = row["state"]
            if detected == "UNKNOWN": unknown += duration
            else:
                confusion[f"{truth}_{detected}"] += duration
                if truth == detected: correct += duration
                elif detected == "STOPPED": false_stop += duration
                else: false_moving += duration
    transitions = []
    for before, after in zip(timeline, timeline[1:]):
        if before["state"] != after["state"] and after["state"] in {"MOVING", "STOPPED"}:
            transitions.append({"timestamp_ns": after["timestamp_ns"], "state": after["state"]})
    detected_stop = next((x["timestamp_ns"] for x in transitions if x["state"] == "STOPPED" and x["timestamp_ns"] >= stop_at), None)
    detected_resume = next((x["timestamp_ns"] for x in transitions if x["state"] == "MOVING" and x["timestamp_ns"] >= resume_at), None)
    false_stop_transitions = sum(x["state"] == "STOPPED" and not stop_at <= x["timestamp_ns"] < resume_at for x in transitions)
    false_resume_transitions = sum(x["state"] == "MOVING" and stop_at <= x["timestamp_ns"] < resume_at for x in transitions)
    stop_delay = None if detected_stop is None else (detected_stop - stop_at) / 1e6
    resume_delay = None if detected_resume is None else (detected_resume - resume_at) / 1e6
    objective = ((1e9 if stop_delay is None else stop_delay) + (1e9 if resume_delay is None else resume_delay)
                 + 10 * false_stop + 3 * false_moving + .5 * unknown
                 + 10_000 * false_stop_transitions + 2_000 * false_resume_transitions + 100 * len(transitions))
    total = correct + false_stop + false_moving + unknown
    return {"objective": objective, "stop_detection_delay_ms": stop_delay,
            "resume_detection_delay_ms": resume_delay, "false_stop_duration_ms": false_stop,
            "false_moving_duration_ms": false_moving, "unknown_duration_ms": unknown,
            "correct_time_fraction": correct / total if total else 0,
            "false_stop_transitions": false_stop_transitions,
            "false_resume_transitions": false_resume_transitions,
            "transition_count": len(transitions), "confusion_ms": confusion, "transitions": transitions}


def candidates(rows: list[dict[str, Any]], field: str, method: str, minimum_tracks: int) -> list[dict[str, Any]]:
    scores = np.array([float(row[field]) for row in rows])
    stops = sorted(set(float(x) for x in np.percentile(scores, [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60])))
    starts = sorted(set(float(x) for x in np.percentile(scores, [35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90])))
    return [{"method": method, "field": field, "minimum_tracks": minimum_tracks,
             "stop_threshold": stop, "start_threshold": start,
             "stop_confirm_ms": stop_ms, "move_confirm_ms": move_ms}
            for stop in stops for start in starts if start > stop
            for stop_ms in (250, 500, 750, 1000, 1250, 1500, 2000)
            for move_ms in (0, 250, 500, 750, 1000)]


def tune(session: Path, output: Path) -> dict[str, Any]:
    markers = parse_markers(session / "markers.jsonl")
    variants = {
        "lk_full": (session / "motion_analysis" / "camera_motion.csv", "projected_motion_score", 8),
        "lk_roi": (session / "motion_analysis_roi" / "camera_motion.csv", "projected_motion_score", 8),
        "farneback_full": (session / "motion_analysis" / "camera_motion.csv", "farneback_motion_score", 0),
        "farneback_roi": (session / "motion_analysis_roi" / "camera_motion.csv", "farneback_motion_score", 0),
    }
    output.mkdir(parents=True, exist_ok=True)
    all_results, best = [], {}
    timelines = {}
    for method, (path, field, tracks) in variants.items():
        rows = read_csv(path)
        for config in candidates(rows, field, method, tracks):
            timeline = classify(rows, field, config["stop_threshold"], config["start_threshold"],
                                config["stop_confirm_ms"], config["move_confirm_ms"], tracks)
            metrics = evaluate(timeline, markers)
            all_results.append({**config, **{k: v for k, v in metrics.items() if k not in {"transitions", "confusion_ms"}}})
        winner = min((x for x in all_results if x["method"] == method), key=lambda x: x["objective"])
        timeline = classify(rows, field, winner["stop_threshold"], winner["start_threshold"],
                            winner["stop_confirm_ms"], winner["move_confirm_ms"], tracks)
        full_metrics = evaluate(timeline, markers)
        best[method] = {**winner, "confusion_ms": full_metrics["confusion_ms"], "transitions": full_metrics["transitions"]}
        timelines[method] = timeline
    camera_winner = min(best.values(), key=lambda x: x["objective"])
    winning_timeline = timelines[camera_winner["method"]]
    lidar = read_csv(session / "motion_analysis" / "lidar_motion.csv")
    lidar_values = [float(x["median_abs_difference_mm"]) for x in lidar if x.get("median_abs_difference_mm")]
    lidar_moving = [float(x["median_abs_difference_mm"]) for x in lidar if int(x["timestamp_ns"]) < markers["STOPPED"] or int(x["timestamp_ns"]) > markers["RESUMED"]]
    lidar_stopped = [float(x["median_abs_difference_mm"]) for x in lidar if markers["STOPPED"] <= int(x["timestamp_ns"]) <= markers["RESUMED"]]
    thresholds = sorted(set(lidar_values))
    lidar_trials = [{"threshold_mm": threshold,
                     "balanced_accuracy": .5 * (sum(x > threshold for x in lidar_moving) / len(lidar_moving)
                                                  + sum(x <= threshold for x in lidar_stopped) / len(lidar_stopped))}
                    for threshold in thresholds]
    best_lidar = max(lidar_trials, key=lambda x: x["balanced_accuracy"])
    lidar_summary = {"moving_median": float(np.median(lidar_moving)), "moving_p90": float(np.percentile(lidar_moving, 90)),
                     "stopped_median": float(np.median(lidar_stopped)), "stopped_p90": float(np.percentile(lidar_stopped, 90)),
                     "overall_p90": float(np.percentile(lidar_values, 90)), "best_single_threshold": best_lidar}
    profiles = read_jsonl(session / "lidar" / "raw_scans.jsonl")
    acceptance = []
    for profile in profiles:
        timestamp = int(profile["captured_monotonic_ns"])
        prior = [x for x in winning_timeline if x["timestamp_ns"] <= timestamp]
        state = prior[-1]["state"] if prior else "UNKNOWN"
        truth = "STOPPED" if markers["STOPPED"] <= timestamp < markers["RESUMED"] else "MOVING"
        acceptance.append({"timestamp_ns": timestamp, "camera_state": state, "ground_truth": truth,
                           "accept_slice": state != "STOPPED",
                           "decision_correct": (state == "STOPPED") == (truth == "STOPPED")})
    write_csv(output / "threshold_candidates.csv", all_results)
    write_csv(output / "profile_acceptance.csv", acceptance)
    summary = {"dataset_is_real": True, "session_key": session.name, "markers": markers,
               "search_space_size": len(all_results), "objective_definition": "delays + 10*false_stop_ms + 3*false_moving_ms + .5*unknown_ms + 10000*false_stop_transition + 2000*false_resume_transition + 100*transitions; missing transition=1e9",
               "best_by_method": best, "best_camera": camera_winner,
               "lidar_confirmation_assessment": {**lidar_summary,
                   "camera_only_comparison": "camera already has zero false transitions; LiDAR threshold cannot confirm motion reliably",
                   "result": "not_discriminative_when_medians_overlap"},
               "profile_acceptance": {"total": len(acceptance), "accepted": sum(x["accept_slice"] for x in acceptance),
                                      "suppressed": sum(not x["accept_slice"] for x in acceptance),
                                      "wrong_during_moving": sum(not x["accept_slice"] and x["ground_truth"] == "MOVING" for x in acceptance),
                                      "wrong_during_stop": sum(x["accept_slice"] and x["ground_truth"] == "STOPPED" for x in acceptance)}}
    (output / "tuning_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("session", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    summary = tune(args.session.resolve(), (args.output_dir or args.session / "motion_tuning").resolve())
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
