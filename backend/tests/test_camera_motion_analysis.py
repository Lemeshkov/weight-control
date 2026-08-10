import csv
import hashlib
import json

import cv2
import numpy as np

from scripts.analyze_camera_lidar_session import nearest_matches
from scripts.analyze_camera_motion import (
    MotionFSM,
    fusion_rule,
    lidar_similarity,
    lk_pair,
    load_frame_rows,
    parse_markers,
    robust_track_metrics,
    analyze,
)


def test_marker_parsing_uses_monotonic_ground_truth(tmp_path):
    path = tmp_path / "markers.jsonl"
    records = [
        {"captured_monotonic_ns": 100, "payload": {"label": "STOPPED"}},
        {"captured_monotonic_ns": 300, "payload": {"label": "RESUMED"}},
    ]
    path.write_text("\n".join(json.dumps(item) for item in records), encoding="utf-8")
    assert parse_markers(path) == {"STOPPED": 100, "RESUMED": 300}


def test_frame_rows_are_ordered_by_timestamp_and_hash_verified(tmp_path):
    camera = tmp_path / "camera"; camera.mkdir()
    for name, content in (("a.jpg", b"a"), ("b.jpg", b"b")):
        (camera / name).write_bytes(content)
    with (camera / "frames.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["captured_monotonic_ns", "file", "jpeg_sha256"])
        writer.writeheader()
        writer.writerow({"captured_monotonic_ns": 200, "file": "b.jpg", "jpeg_sha256": hashlib.sha256(b"b").hexdigest()})
        writer.writerow({"captured_monotonic_ns": 100, "file": "a.jpg", "jpeg_sha256": hashlib.sha256(b"a").hexdigest()})
    assert [row["captured_monotonic_ns"] for row in load_frame_rows(tmp_path)] == [100, 200]


def test_lk_tracks_known_translation():
    previous = np.zeros((120, 160), dtype=np.uint8)
    for x in range(20, 140, 30):
        for y in range(20, 100, 30):
            cv2.circle(previous, (x, y), 3, 255, -1)
    matrix = np.float32([[1, 0, 4], [0, 1, 2]])
    current = cv2.warpAffine(previous, matrix, (160, 120))
    metrics, _ = lk_pair(previous, current, 0.25, clahe=False)
    assert metrics["tracks_valid"] >= 6
    assert abs(metrics["median_dx"] - 4) < 0.5
    assert abs(metrics["median_dy"] - 2) < 0.5


def test_forward_backward_rejection(monkeypatch):
    features = np.array([[[10.0, 10.0]], [[20.0, 20.0]]], dtype=np.float32)
    forward = features + np.array([[[2.0, 0.0]]], dtype=np.float32)
    backward = np.array([[[10.0, 10.0]], [[99.0, 99.0]]], dtype=np.float32)
    calls = iter([(forward, np.ones((2, 1), np.uint8), None), (backward, np.ones((2, 1), np.uint8), None)])
    monkeypatch.setattr(cv2, "goodFeaturesToTrack", lambda *_args, **_kwargs: features)
    monkeypatch.setattr(cv2, "calcOpticalFlowPyrLK", lambda *_args, **_kwargs: next(calls))
    metrics, vectors = lk_pair(np.zeros((30, 30), np.uint8), np.zeros((30, 30), np.uint8), 0.2, clahe=False)
    assert metrics["tracks_valid"] == 1
    assert vectors.tolist() == [[2.0, 0.0]]


def test_motion_score_uses_robust_median_not_outlier_mean():
    metrics = robust_track_metrics(np.array([[2.0, 0], [2.0, 0], [100.0, 0]]), 0.5)
    assert metrics["median_magnitude"] == 2.0
    assert metrics["motion_score"] == 4.0


def test_hysteresis_stop_and_resume_transitions():
    fsm = MotionFSM(2, 5, stop_confirm_ms=500, move_confirm_ms=300, minimum_valid_tracks=3)
    assert fsm.update(0, 10, 10) == "MOVING"
    assert fsm.update(100_000_000, 1, 10) == "STOP_CANDIDATE"
    assert fsm.update(700_000_000, 1, 10) == "STOPPED"
    assert fsm.update(800_000_000, 8, 10) == "MOVE_CANDIDATE"
    assert fsm.update(1_200_000_000, 8, 10) == "MOVING"


def test_lidar_similarity_preserves_common_beam_indexes():
    result = lidar_similarity(
        {"ranges_mm": [1000, None, 2000, 3000]},
        {"ranges_mm": [1010, 999, 1980, None]},
    )
    assert result["common_valid_beams"] == 2
    assert result["median_abs_difference_mm"] == 15.0


def test_timestamp_matching_and_deterministic_fusion():
    matches = nearest_matches(
        [{"sequence_number": 1, "captured_utc": "x", "captured_monotonic_ns": 120}],
        [{"sequence_number": 2, "captured_monotonic_ns": 100}, {"sequence_number": 3, "captured_monotonic_ns": 200}],
    )
    assert matches[0]["camera_sequence"] == 2
    assert fusion_rule("STOPPED", 0.9, "STOPPED")[0] == "STOPPED"
    assert fusion_rule("MOVING", 0.9, "STOPPED")[0] == "UNKNOWN"


def test_offline_analyzer_writes_all_artifacts(tmp_path):
    session = tmp_path / "session"; camera = session / "camera"; lidar = session / "lidar"
    camera.mkdir(parents=True); lidar.mkdir()
    (session / "manifest.json").write_text(json.dumps({
        "session_key": "fixture", "record_counts": {"events": 1, "markers": 2}
    }), encoding="utf-8")
    (session / "events.jsonl").write_text(json.dumps({"event": "SESSION_OPENED"}) + "\n", encoding="utf-8")
    markers = [
        {"captured_monotonic_ns": 3_000_000_000, "payload": {"label": "STOPPED"}},
        {"captured_monotonic_ns": 5_000_000_000, "payload": {"label": "RESUMED"}},
    ]
    (session / "markers.jsonl").write_text("\n".join(json.dumps(item) for item in markers), encoding="utf-8")
    base = np.zeros((100, 140), np.uint8)
    for x in range(15, 125, 20):
        for y in range(15, 85, 20): cv2.circle(base, (x, y), 2, 255, -1)
    shifts = [0, 3, 6, 6, 6, 9, 12]
    frame_rows = []
    for index, shift in enumerate(shifts, start=1):
        image = cv2.warpAffine(base, np.float32([[1, 0, shift], [0, 1, 0]]), (140, 100))
        file = f"frame_{index:03d}.jpg"; cv2.imwrite(str(camera / file), image)
        content = (camera / file).read_bytes()
        frame_rows.append({"captured_monotonic_ns": index * 1_000_000_000, "captured_utc": str(index), "file": file, "jpeg_sha256": hashlib.sha256(content).hexdigest()})
    with (camera / "frames.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=frame_rows[0]); writer.writeheader(); writer.writerows(frame_rows)
    profiles = []
    for index, value in enumerate((1000, 1020, 1040, 1040, 1040, 1060, 1080), start=1):
        profiles.append({"captured_monotonic_ns": index * 1_000_000_000, "ranges_mm": [value, value + 10, value + 20]})
    (lidar / "raw_scans.jsonl").write_text("\n".join(json.dumps(item) for item in profiles), encoding="utf-8")

    output = tmp_path / "output"
    summary = analyze(session, output, verify_hashes=True, run_farneback=False)

    assert summary["session_key"] == "fixture"
    assert summary["lidar_profiles"]["during_stop"] == 3
    for name in ("motion_summary.json", "camera_motion.csv", "lidar_motion.csv", "fusion_motion.csv", "motion_plot.png"):
        assert (output / name).is_file()
