"""Validate the frozen TEST B camera-motion candidate on an unseen session.

This module is offline-only.  It deliberately contains no threshold search or
dataset-derived configuration.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np

try:
    from scripts.analyze_camera_motion import farneback_pair, load_frame_rows, read_jsonl, write_csv
except ModuleNotFoundError:  # Direct invocation from backend/scripts.
    from analyze_camera_motion import farneback_pair, load_frame_rows, read_jsonl, write_csv


TUNING_SESSION_KEY = "9fafd185315e4b8194d7b59b5afb6f39"
Scenario = Literal["stop-resume", "no-stop"]


@dataclass(frozen=True)
class FrozenFarnebackCandidate:
    algorithm: str = "Farneback full-frame"
    stop_threshold: float = 1.361371e-05
    start_threshold: float = 0.00887307
    stop_confirmation_ms: int = 2000
    resume_confirmation_ms: int = 750


@dataclass(frozen=True)
class ValidationCriteria:
    stop_detection_delay_max_ms: int = 3000
    resume_detection_delay_max_ms: int = 1500
    moving_profiles_incorrectly_frozen_max_fraction: float = 0.05
    stationary_profiles_incorrectly_accepted_max_fraction: float = 0.15
    correct_time_min_fraction: float = 0.90


FIXED_CANDIDATE = FrozenFarnebackCandidate()
FIXED_CRITERIA = ValidationCriteria()
PRESENCE_MARKERS = ("VEHICLE_ENTERED", "VEHICLE_EXITED")
STOP_RESUME_MARKERS = ("VEHICLE_ENTERED", "STOPPED", "RESUMED", "VEHICLE_EXITED")


def parse_ground_truth(path: Path, scenario: Scenario) -> tuple[dict[str, int], list[str]]:
    found: dict[str, int] = {}
    if path.is_file():
        for record in read_jsonl(path):
            label = str(record.get("payload", {}).get("label", record.get("label", ""))).upper()
            if label in STOP_RESUME_MARKERS:
                if label in found:
                    return found, [f"DUPLICATE_{label}"]
                found[label] = int(record["captured_monotonic_ns"])
    required = PRESENCE_MARKERS if scenario == "no-stop" else STOP_RESUME_MARKERS
    missing = [label for label in required if label not in found]
    if missing:
        return found, missing
    timestamps = [found[label] for label in required]
    if any(right <= left for left, right in zip(timestamps, timestamps[1:])):
        return found, ["INVALID_MARKER_ORDER"]
    return found, []


def fixed_hysteresis(rows: list[dict[str, Any]], candidate: FrozenFarnebackCandidate = FIXED_CANDIDATE) -> list[dict[str, Any]]:
    state: str = "MOVING"
    candidate_state: str | None = None
    candidate_since: int | None = None
    result = []
    for row in rows:
        timestamp = int(row["timestamp_ns"])
        score = float(row["motion_score"])
        wanted = "STOPPED" if score <= candidate.stop_threshold else "MOVING" if score >= candidate.start_threshold else None
        if wanted == state:
            candidate_state = candidate_since = None
        elif wanted is not None:
            if candidate_state != wanted:
                candidate_state, candidate_since = wanted, timestamp
            confirmation = candidate.stop_confirmation_ms if wanted == "STOPPED" else candidate.resume_confirmation_ms
            if (timestamp - int(candidate_since)) / 1e6 >= confirmation:
                state = wanted
                candidate_state = candidate_since = None
        result.append({**row, "predicted_state": state,
                       "candidate_state": candidate_state or "",
                       "stop_threshold": candidate.stop_threshold,
                       "start_threshold": candidate.start_threshold})
    return result


def transitions(timeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"timestamp_ns": int(after["timestamp_ns"]), "state": after["predicted_state"]}
            for before, after in zip(timeline, timeline[1:])
            if before["predicted_state"] != after["predicted_state"]]


def truth_at(timestamp: int, scenario: Scenario, ground_truth: dict[str, int]) -> str:
    required = PRESENCE_MARKERS if scenario == "no-stop" else STOP_RESUME_MARKERS
    if any(label not in ground_truth for label in required):
        return "UNKNOWN"
    entered, exited = ground_truth["VEHICLE_ENTERED"], ground_truth["VEHICLE_EXITED"]
    if timestamp < entered or timestamp >= exited:
        return "NO_VEHICLE"
    if scenario == "no-stop":
        return "MOVING"
    return "STOPPED" if ground_truth["STOPPED"] <= timestamp < ground_truth["RESUMED"] else "MOVING"


def duration_metrics(timeline: list[dict[str, Any]], scenario: Scenario,
                     ground_truth: dict[str, int]) -> dict[str, Any]:
    confusion = {"MOVING_MOVING": 0.0, "MOVING_STOPPED": 0.0,
                 "STOPPED_MOVING": 0.0, "STOPPED_STOPPED": 0.0,
                 "UNKNOWN": 0.0}
    stopped_runs, current_run = [], 0.0
    excluded_before = excluded_after = vehicle_present = 0.0
    for index, row in enumerate(timeline[:-1]):
        left, right = int(row["timestamp_ns"]), int(timeline[index + 1]["timestamp_ns"])
        boundaries = [left]
        boundaries += [value for value in ground_truth.values() if left < value < right]
        boundaries.append(right)
        for start, end in zip(sorted(boundaries), sorted(boundaries)[1:]):
            duration = (end - start) / 1e6
            actual = truth_at(start, scenario, ground_truth)
            predicted = row["predicted_state"]
            if actual == "NO_VEHICLE":
                if start < ground_truth.get("VEHICLE_ENTERED", start): excluded_before += duration
                else: excluded_after += duration
                if current_run: stopped_runs.append(current_run); current_run = 0.0
                continue
            if actual != "UNKNOWN": vehicle_present += duration
            if actual == "UNKNOWN" or predicted == "UNKNOWN":
                confusion["UNKNOWN"] += duration
            else:
                confusion[f"{actual}_{predicted}"] += duration
            if predicted == "STOPPED":
                current_run += duration
            elif current_run:
                stopped_runs.append(current_run); current_run = 0.0
    if current_run:
        stopped_runs.append(current_run)
    changed = [item for item in transitions(timeline)
               if truth_at(item["timestamp_ns"], scenario, ground_truth) not in {"NO_VEHICLE", "UNKNOWN"}]
    total = sum(confusion.values())
    correct = confusion["MOVING_MOVING"] + confusion["STOPPED_STOPPED"]
    metrics: dict[str, Any] = {
        "false_stop_duration_ms": confusion["MOVING_STOPPED"],
        "false_moving_duration_ms": confusion["STOPPED_MOVING"],
        "unknown_duration_ms": confusion["UNKNOWN"],
        "correct_time_fraction": correct / total if total else None,
        "confusion_matrix_time_ms": confusion,
        "total_predicted_transitions": len(changed),
        "predicted_stopped_duration_ms": sum(stopped_runs),
        "maximum_continuous_false_stop_duration_ms": max(stopped_runs, default=0.0) if scenario == "no-stop" else None,
        "vehicle_present_duration_ms": vehicle_present,
        "excluded_before_entry_ms": excluded_before,
        "excluded_after_exit_ms": excluded_after,
    }
    if scenario == "no-stop":
        metrics.update({"predicted_stop_occurred": any(x["state"] == "STOPPED" for x in changed),
                        "false_stop_transitions": sum(x["state"] == "STOPPED" for x in changed),
                        "false_resume_transitions": 0})
        return metrics
    if any(label not in ground_truth for label in STOP_RESUME_MARKERS):
        metrics.update({"manual_stop_timestamp_ns": ground_truth.get("STOPPED"), "manual_resume_timestamp_ns": ground_truth.get("RESUMED")})
        return metrics
    stop, resume = ground_truth["STOPPED"], ground_truth["RESUMED"]
    predicted_stop = next((x["timestamp_ns"] for x in changed if x["state"] == "STOPPED" and x["timestamp_ns"] >= stop), None)
    predicted_resume = next((x["timestamp_ns"] for x in changed if x["state"] == "MOVING" and x["timestamp_ns"] >= resume), None)
    metrics.update({
        "manual_stop_timestamp_ns": stop, "predicted_stop_timestamp_ns": predicted_stop,
        "stop_detection_delay_ms": None if predicted_stop is None else (predicted_stop - stop) / 1e6,
        "manual_resume_timestamp_ns": resume, "predicted_resume_timestamp_ns": predicted_resume,
        "resume_detection_delay_ms": None if predicted_resume is None else (predicted_resume - resume) / 1e6,
        "false_stop_transitions": sum(x["state"] == "STOPPED" and not stop <= x["timestamp_ns"] < resume for x in changed),
        "false_resume_transitions": sum(x["state"] == "MOVING" and stop <= x["timestamp_ns"] < resume for x in changed),
        "ground_truth_stopped_duration_ms": (resume - stop) / 1e6,
    })
    return metrics


def simulate_profiles(profiles: list[dict[str, Any]], timeline: list[dict[str, Any]],
                      scenario: Scenario, ground_truth: dict[str, int]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    result, camera_index = [], -1
    for profile_index, profile in enumerate(profiles):
        timestamp = int(profile["captured_monotonic_ns"])
        while camera_index + 1 < len(timeline) and int(timeline[camera_index + 1]["timestamp_ns"]) <= timestamp:
            camera_index += 1
        predicted = timeline[camera_index]["predicted_state"] if camera_index >= 0 else "UNKNOWN"
        actual = truth_at(timestamp, scenario, ground_truth)
        action = ("EXCLUDE" if actual == "NO_VEHICLE" else
                  "UNKNOWN" if actual == "UNKNOWN" or predicted == "UNKNOWN" else
                  "ACCEPT" if predicted == "MOVING" else "FREEZE")
        result.append({"profile_index": profile_index, "timestamp": timestamp,
                       "ground_truth_state": actual, "predicted_state": predicted,
                       "slice_action": action,
                       "classification_correct": actual != "UNKNOWN" and actual == predicted})
    summary = {
        "total_profiles": len(result),
        "moving_ground_truth_profiles": sum(x["ground_truth_state"] == "MOVING" for x in result),
        "stationary_ground_truth_profiles": sum(x["ground_truth_state"] == "STOPPED" for x in result),
        "accepted_profiles": sum(x["slice_action"] == "ACCEPT" for x in result),
        "frozen_profiles": sum(x["slice_action"] == "FREEZE" for x in result),
        "moving_profiles_incorrectly_frozen": sum(x["ground_truth_state"] == "MOVING" and x["slice_action"] == "FREEZE" for x in result),
        "stationary_profiles_incorrectly_accepted": sum(x["ground_truth_state"] == "STOPPED" and x["slice_action"] == "ACCEPT" for x in result),
        "unknown_profiles": sum(x["slice_action"] == "UNKNOWN" for x in result),
        "excluded_profiles": sum(x["slice_action"] == "EXCLUDE" for x in result),
    }
    return result, summary


def criteria_result(scenario: Scenario, metrics: dict[str, Any], slices: dict[str, int], complete: bool) -> tuple[dict[str, bool | None], str]:
    if not complete:
        return {}, "GROUND_TRUTH_INCOMPLETE"
    if scenario == "no-stop":
        checks = {"false_stop_transitions_zero": metrics["false_stop_transitions"] == 0,
                  "false_stop_duration_zero": metrics["false_stop_duration_ms"] == 0,
                  "moving_profiles_incorrectly_frozen_zero": slices["moving_profiles_incorrectly_frozen"] == 0}
    else:
        moving = slices["moving_ground_truth_profiles"]
        stationary = slices["stationary_ground_truth_profiles"]
        checks = {
            "false_stop_transitions_zero": metrics["false_stop_transitions"] == 0,
            "false_resume_transitions_zero": metrics["false_resume_transitions"] == 0,
            "stop_detection_delay": metrics.get("stop_detection_delay_ms") is not None and metrics["stop_detection_delay_ms"] <= FIXED_CRITERIA.stop_detection_delay_max_ms,
            "resume_detection_delay": metrics.get("resume_detection_delay_ms") is not None and metrics["resume_detection_delay_ms"] <= FIXED_CRITERIA.resume_detection_delay_max_ms,
            "moving_profiles_incorrectly_frozen": bool(moving) and slices["moving_profiles_incorrectly_frozen"] / moving <= FIXED_CRITERIA.moving_profiles_incorrectly_frozen_max_fraction,
            "stationary_profiles_incorrectly_accepted": bool(stationary) and slices["stationary_profiles_incorrectly_accepted"] / stationary <= FIXED_CRITERIA.stationary_profiles_incorrectly_accepted_max_fraction,
            "correct_time_fraction": metrics.get("correct_time_fraction") is not None and metrics["correct_time_fraction"] >= FIXED_CRITERIA.correct_time_min_fraction,
        }
    return checks, "PASS" if all(checks.values()) else "FAIL"


def draw_validation_plot(path: Path, timeline: list[dict[str, Any]], profiles: list[dict[str, Any]], ground_truth: dict[str, int]) -> None:
    width, height, margin = 1600, 720, 70
    image = np.full((height, width, 3), 255, np.uint8)
    timestamps = [int(x["timestamp_ns"]) for x in timeline]
    if not timestamps:
        return
    first, last = min(timestamps), max(timestamps); span = max(last - first, 1)
    xof = lambda value: margin + round((value - first) / span * (width - 2 * margin))
    scores = [float(x["motion_score"]) for x in timeline]
    scale = max(float(np.percentile(scores, 95)), FIXED_CANDIDATE.start_threshold, 1e-9)
    yof = lambda value: height - 190 - round(min(value / scale, 1.2) * (height - 280) / 1.2)
    points = [(xof(int(row["timestamp_ns"])), yof(float(row["motion_score"]))) for row in timeline]
    for a, b in zip(points, points[1:]): cv2.line(image, a, b, (200, 70, 30), 2)
    for value, color, label in ((FIXED_CANDIDATE.stop_threshold, (0, 140, 255), "fixed STOP threshold"),
                                (FIXED_CANDIDATE.start_threshold, (160, 0, 160), "fixed START threshold")):
        y = yof(value); cv2.line(image, (margin, y), (width-margin, y), color, 1); cv2.putText(image, label, (margin+5, y-5), 0, .5, color, 1)
    for label, timestamp in ground_truth.items():
        x = xof(timestamp); cv2.line(image, (x, margin), (x, height-margin), (0, 0, 220), 2); cv2.putText(image, f"manual {label}", (x+5, margin+20), 0, .55, (0, 0, 220), 2)
    for change in transitions(timeline):
        x = xof(change["timestamp_ns"]); cv2.line(image, (x, margin+35), (x, height-margin), (0, 150, 0), 2); cv2.putText(image, f"predicted {change['state']}", (x+5, margin+55), 0, .5, (0, 120, 0), 1)
    for current, following in zip(timeline, timeline[1:]):
        color = (90, 190, 90) if current["predicted_state"] == "MOVING" else (80, 80, 220)
        cv2.rectangle(image, (xof(int(current["timestamp_ns"])), height-155),
                      (xof(int(following["timestamp_ns"])), height-130), color, -1)
    cv2.putText(image, "predicted state: green=MOVING, red=STOPPED", (margin, height-165), 0, .5, (60, 60, 60), 1)
    for profile in profiles:
        timestamp = int(profile["captured_monotonic_ns"])
        if first <= timestamp <= last: cv2.line(image, (xof(timestamp), height-115), (xof(timestamp), height-95), (120, 120, 120), 1)
    cv2.putText(image, "LiDAR profile timestamps", (margin, height-75), 0, .55, (80, 80, 80), 1)
    cv2.imwrite(str(path), image)


def validate(session: Path, scenario: Scenario, output: Path | None = None) -> dict[str, Any]:
    manifest = json.loads((session / "manifest.json").read_text(encoding="utf-8"))
    session_key = str(manifest.get("session_key") or session.name)
    ground_truth, missing = parse_ground_truth(session / "markers.jsonl", scenario)
    metric_ground_truth = ground_truth if not missing else {}
    frame_rows = load_frame_rows(session, verify_hashes=True)
    camera_scores, previous = [], None
    for frame in frame_rows:
        image = cv2.imread(frame["path"], cv2.IMREAD_GRAYSCALE)
        if image is None: raise ValueError(f"cannot decode JPEG: {frame['path']}")
        if previous is not None:
            dt = (int(frame["captured_monotonic_ns"]) - previous[0]) / 1e9
            score = farneback_pair(previous[1], image, dt)
            camera_scores.append({"timestamp_ns": int(frame["captured_monotonic_ns"]),
                                  "captured_utc": frame.get("captured_utc", ""),
                                  "dt_ms": dt * 1000, "motion_score": score["farneback_motion_score"],
                                  "farneback_p90": score["farneback_p90"], "cpu_ms": score["farneback_cpu_ms"]})
        previous = (int(frame["captured_monotonic_ns"]), image)
    timeline = fixed_hysteresis(camera_scores)
    for row in timeline:
        row["ground_truth_state"] = truth_at(int(row["timestamp_ns"]), scenario, metric_ground_truth)
    metrics = duration_metrics(timeline, scenario, metric_ground_truth)
    scores = np.array([x["motion_score"] for x in timeline])
    metrics["motion_score_distribution"] = {"minimum": float(np.min(scores)), "p01": float(np.percentile(scores, 1)),
                                             "p05": float(np.percentile(scores, 5)), "p10": float(np.percentile(scores, 10))}
    profiles = read_jsonl(session / "lidar" / "raw_scans.jsonl")
    profile_rows, slice_summary = simulate_profiles(profiles, timeline, scenario, metric_ground_truth)
    complete = not missing
    checks, overall = criteria_result(scenario, metrics, slice_summary, complete)
    dataset_role = "TUNING" if session_key == TUNING_SESSION_KEY else "VALIDATION"
    report = {
        "dataset_role": dataset_role,
        "independent_validation_eligible": dataset_role == "VALIDATION",
        "session_key": session_key, "scenario": scenario,
        "algorithm": FIXED_CANDIDATE.algorithm, "algorithm_parameters": asdict(FIXED_CANDIDATE),
        "ground_truth": {"status": "COMPLETE" if complete else "INCOMPLETE", "missing": missing, **ground_truth},
        "metrics": metrics, "lidar_slice_simulation": slice_summary,
        "validation_criteria": asdict(FIXED_CRITERIA), "criteria_results": checks,
        "overall_result": overall,
    }
    destination = output or session / "motion_validation"
    destination.mkdir(parents=True, exist_ok=True)
    write_csv(destination / "camera_validation.csv", timeline)
    write_csv(destination / "profile_acceptance.csv", profile_rows)
    draw_validation_plot(destination / "validation_plot.png", timeline, profiles, ground_truth)
    (destination / "validation_summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    parser.add_argument("--scenario", required=True, choices=("stop-resume", "no-stop"))
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    report = validate(args.session.resolve(), args.scenario, args.output_dir.resolve() if args.output_dir else None)
    print(json.dumps({"session_key": report["session_key"], "dataset_role": report["dataset_role"],
                      "overall_result": report["overall_result"],
                      "report": str((args.output_dir or args.session / 'motion_validation') / 'validation_summary.json')}, ensure_ascii=False))


if __name__ == "__main__":
    main()
