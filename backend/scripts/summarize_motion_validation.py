"""Aggregate offline camera-motion validation reports without counting tuning data."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def summarize(root: Path) -> dict:
    reports = []
    for path in sorted(root.rglob("motion_validation/validation_summary.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        metrics, slices = report.get("metrics", {}), report.get("lidar_slice_simulation", {})
        reports.append({"session": report.get("session_key"), "dataset_role": report.get("dataset_role"),
                        "scenario": report.get("scenario"), "result": report.get("overall_result"),
                        "stop_delay_ms": metrics.get("stop_detection_delay_ms"),
                        "resume_delay_ms": metrics.get("resume_detection_delay_ms"),
                        "false_stop_ms": metrics.get("false_stop_duration_ms"),
                        "false_moving_ms": metrics.get("false_moving_duration_ms"),
                        "incorrect_frozen_profiles": slices.get("moving_profiles_incorrectly_frozen"),
                        "incorrect_accepted_stationary_profiles": slices.get("stationary_profiles_incorrectly_accepted"),
                        "correct_fraction": metrics.get("correct_time_fraction"), "report_path": str(path)})
    validation = [row for row in reports if row["dataset_role"] == "VALIDATION"]
    return {"reports": reports, "validation_only": {"total": len(validation),
            "pass": sum(row["result"] == "PASS" for row in validation),
            "fail": sum(row["result"] == "FAIL" for row in validation),
            "incomplete": sum(row["result"] == "GROUND_TRUTH_INCOMPLETE" for row in validation)}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path); args = parser.parse_args()
    summary = summarize(args.root.resolve())
    output = args.output or args.root / "motion_validation_summary.json"
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = output.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        fields = list(summary["reports"][0]) if summary["reports"] else ["session"]
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(summary["reports"])
    print(json.dumps({"output": str(output), **summary["validation_only"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
