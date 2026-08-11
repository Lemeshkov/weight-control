from pathlib import Path

import cv2
import numpy as np
import pytest

from scripts.evaluate_weighbridge_vehicle_detector import presence_metrics
from scripts.prepare_weighbridge_vehicle_dataset import classify
from scripts.validate_weighbridge_vehicle_dataset import validate
from scripts.weighbridge_vehicle_dataset import parse_yolo_label, select_diverse


def image(path: Path, value: int) -> None:
    cv2.imwrite(str(path), np.full((32, 32, 3), value, np.uint8))


def test_frame_selection_suppresses_close_duplicates(tmp_path):
    rows = []
    for index, value in enumerate((10, 10, 10, 200)):
        path = tmp_path / f"{index}.jpg"; image(path, value)
        if index == 3:
            changed = cv2.imread(str(path)); changed[:, :16] = 0; cv2.imwrite(str(path), changed)
        rows.append({"source": path, "timestamp_ns": index * 100_000_000})
    selected = select_diverse(rows, 4, min_gap_ms=500, min_hash_distance=4)
    assert len(selected) == 2


def test_negative_and_active_classification():
    markers = {"VEHICLE_ENTERED": 100, "STOPPED": 200, "RESUMED": 300, "VEHICLE_EXITED": 400}
    assert classify(50, markers) == ("false", "no_vehicle_outside_enter_exit", "VERIFIED_NEGATIVE")
    assert classify(250, markers) == ("true", "stopped_vehicle", "BBOX_REQUIRED")
    assert classify(450, markers)[0] == "false"
    assert classify(250, {})[0] == "unknown"


def test_yolo_parser_and_bbox_validation(tmp_path):
    valid = tmp_path / "valid.txt"; valid.write_text("0 0.5 0.5 0.4 0.2\n", encoding="utf-8")
    assert parse_yolo_label(valid)[0][0] == 0
    invalid = tmp_path / "invalid.txt"; invalid.write_text("0 0.1 0.5 0.4 0.2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="outside"): parse_yolo_label(invalid)


def make_dataset(root: Path, duplicate_across_split: bool = False) -> None:
    rows = []
    for split, session, value in (("train", "s1", 20), ("val", "s2", 120), ("test", "s3", 220)):
        (root / "images" / split).mkdir(parents=True); (root / "labels" / split).mkdir(parents=True)
        path = root / "images" / split / f"{session}.jpg"; image(path, 20 if duplicate_across_split else value)
        (root / "labels" / split / f"{session}.txt").write_text("" if split == "test" else "0 .5 .5 .5 .5\n", encoding="utf-8")
        rows.append(f"images/{split}/{session}.jpg,{session},{session}.jpg,1,true,test,{split},DEV,COMPLETE")
    (root / "dataset_manifest.csv").write_text(
        "dataset_image,source_session,source_frame,timestamp,vehicle_present_ground_truth,selection_reason,split,dataset_role,annotation_status\n" + "\n".join(rows), encoding="utf-8")


def test_manifest_session_split_and_leakage_validation(tmp_path):
    make_dataset(tmp_path)
    report = validate(tmp_path)
    assert report["valid"] and report["labeled_positive_images"] == 2 and report["labeled_negative_images"] == 1
    # A manifest edit that puts one pass into another split must be rejected.
    manifest = tmp_path / "dataset_manifest.csv"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace("images/val/s2.jpg,s2", "images/val/s2.jpg,s1"), encoding="utf-8")
    assert any("session leakage" in error for error in validate(tmp_path)["errors"])


def test_exact_duplicate_across_splits_is_leakage(tmp_path):
    make_dataset(tmp_path, duplicate_across_split=True)
    assert any("exact duplicate leakage" in error for error in validate(tmp_path)["errors"])


def test_presence_and_gap_metrics():
    rows = [
        {"source_session":"s", "timestamp_ns":0, "ground_truth_present":True, "detected":True, "confidence":.9, "center_x":.4, "center_y":.5},
        {"source_session":"s", "timestamp_ns":250_000_000, "ground_truth_present":True, "detected":False, "confidence":0, "center_x":None, "center_y":None},
        {"source_session":"s", "timestamp_ns":500_000_000, "ground_truth_present":True, "detected":True, "confidence":.8, "center_x":.5, "center_y":.5},
        {"source_session":"s", "timestamp_ns":750_000_000, "ground_truth_present":False, "detected":False, "confidence":0, "center_x":None, "center_y":None},
    ]
    metrics = presence_metrics(rows)
    assert metrics["presence_recall"] == pytest.approx(2 / 3)
    assert metrics["longest_missed_frame_run"] == 1
    assert metrics["negative_false_positive_rate"] == 0
