"""Select diverse real frames into an ignored, annotation-ready YOLO dataset."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

try:
    from scripts.weighbridge_vehicle_dataset import presence_markers, read_frames, select_diverse, write_csv
except ModuleNotFoundError:
    from weighbridge_vehicle_dataset import presence_markers, read_frames, select_diverse, write_csv

SESSION_PLAN = {
    "c1788407a99c40a88e4d9f85b5435ca5": ("train", "TRAIN", 160),
    "82c7f151a10e4b67a8a4d934ffc72288": ("train", "TRAIN", 70),
    "9fafd185315e4b8194d7b59b5afb6f39": ("train", "TRAIN", 55),
    "c65c0b53513d4c64a43d7469a7d1bc73": ("val", "DEV", 100),
    "0700fa3a0c254fdf9edbed8f13acab07": ("test", "TEST", 70),
}
FIELDS = ["dataset_image", "source_session", "source_frame", "timestamp", "vehicle_present_ground_truth",
          "selection_reason", "split", "dataset_role", "annotation_status"]


def classify(timestamp: int, markers: dict[str, int]) -> tuple[str, str, str]:
    entered, exited = markers.get("VEHICLE_ENTERED"), markers.get("VEHICLE_EXITED")
    if entered is None or exited is None:
        return "unknown", "legacy_session_manual_presence_review", "REVIEW_REQUIRED"
    if timestamp < entered or timestamp >= exited:
        return "false", "no_vehicle_outside_enter_exit", "VERIFIED_NEGATIVE"
    stopped, resumed = markers.get("STOPPED"), markers.get("RESUMED")
    phase = "vehicle_active"
    if stopped and timestamp < stopped: phase = "entry_and_moving"
    elif stopped and resumed and timestamp < resumed: phase = "stopped_vehicle"
    elif resumed: phase = "resumed_and_exit"
    return "true", phase, "BBOX_REQUIRED"


def prepare(source_root: Path, output_root: Path, *, clean: bool = False) -> dict:
    if clean and output_root.exists():
        shutil.rmtree(output_root)
    for split in ("train", "val", "test"):
        (output_root / "images" / split).mkdir(parents=True, exist_ok=True)
        (output_root / "labels" / split).mkdir(parents=True, exist_ok=True)
    manifest = []
    inventory = {p.name: len(read_frames(p)) for p in source_root.iterdir()
                 if p.is_dir() and (p / "camera" / "frames.csv").exists()}
    for session_key, (split, role, limit) in SESSION_PLAN.items():
        session = source_root / session_key
        if not session.exists():
            continue
        markers = presence_markers(session)
        rows = read_frames(session)
        # The fully marked pass is stratified so negatives cannot crowd out the short active interval.
        if {"VEHICLE_ENTERED", "VEHICLE_EXITED"} <= markers.keys():
            active = [r for r in rows if markers["VEHICLE_ENTERED"] <= r["timestamp_ns"] < markers["VEHICLE_EXITED"]]
            negative = [r for r in rows if r not in active]
            selected = select_diverse(active, round(limit * .65)) + select_diverse(negative, limit - round(limit * .65))
            selected.sort(key=lambda row: row["timestamp_ns"])
        else:
            selected = select_diverse(rows, limit)
        for row in selected:
            truth, reason, status = classify(row["timestamp_ns"], markers)
            name = f"{session_key}_{row['source'].name}"
            destination = output_root / "images" / split / name
            shutil.copy2(row["source"], destination)
            if status == "VERIFIED_NEGATIVE":
                (output_root / "labels" / split / f"{Path(name).stem}.txt").write_text("", encoding="utf-8")
            manifest.append({"dataset_image": destination.relative_to(output_root).as_posix(),
                             "source_session": session_key, "source_frame": row["source"].name,
                             "timestamp": row["timestamp_ns"], "vehicle_present_ground_truth": truth,
                             "selection_reason": reason, "split": split, "dataset_role": role,
                             "annotation_status": status})
    write_csv(output_root / "dataset_manifest.csv", manifest, FIELDS)
    (output_root / "data.yaml").write_text("path: .\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: weighbridge_vehicle\n", encoding="utf-8")
    summary = {"available_sessions": len(inventory), "available_frames": sum(inventory.values()),
               "selected_frames": len(manifest), "verified_positive_candidates": sum(r["vehicle_present_ground_truth"] == "true" for r in manifest),
               "verified_negatives": sum(r["vehicle_present_ground_truth"] == "false" for r in manifest),
               "manual_presence_review": sum(r["vehicle_present_ground_truth"] == "unknown" for r in manifest),
               "independent_test_available": False,
               "note": "All selected sessions were previously inspected; TEST is an internal development test, not unseen validation."}
    (output_root / "preparation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnostics", type=Path, default=Path("../diagnostics"))
    parser.add_argument("--output", type=Path, default=Path("../diagnostics/training/weighbridge_vehicle/dataset"))
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args(); print(json.dumps(prepare(args.diagnostics.resolve(), args.output.resolve(), clean=args.clean), indent=2))


if __name__ == "__main__": main()
