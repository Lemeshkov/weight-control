import csv
import json
import time
from pathlib import Path

import numpy as np

from scripts.analyze_camera_lidar_session import analyze_session, nearest_matches
from services.camera_client import CV2_AVAILABLE, CameraClient
from services.camera_lidar_diagnostic_recorder import CameraLidarDiagnosticRecorder
from services.lidar_client import LidarClient


def telegram(ranges):
    return "sRA LMDscandata DIST1 3F800000 00000000 FFF92230 1388 %X %s" % (
        len(ranges), " ".join(f"{value:X}" for value in ranges)
    )


def test_raw_format_preserves_beam_indexes_and_invalid_values():
    parsed = LidarClient().parse_diagnostic_scan(telegram([1000, 0, 2000, 9999]))
    assert parsed["beam_count"] == 4
    assert parsed["ranges_raw"] == [1000, 0, 2000, 9999]
    assert parsed["ranges_mm"] == [1000, None, 2000, None]
    assert parsed["valid_mask"] == [True, False, True, False]


def test_disabled_recorder_creates_nothing(tmp_path):
    recorder = CameraLidarDiagnosticRecorder(enabled=False, base_dir=tmp_path)
    recorder.start("disabled", started_at="2026-08-09T00:00:00+00:00")
    assert not (tmp_path / "disabled").exists()


def test_enabled_recorder_flushes_bind_and_partial_metadata(tmp_path):
    recorder = CameraLidarDiagnosticRecorder(enabled=True, base_dir=tmp_path, queue_size=10, max_duration_sec=1, max_bytes=1)
    recorder.start("pass", started_at="2026-08-09T00:00:00+00:00")
    recorder.bind_trip(42)
    recorder._queue.join()
    recorder.record_lidar({"sequence_number": 1, "captured_monotonic_ns": time.monotonic_ns()})
    recorder.stop()
    manifest = json.loads((tmp_path / "pass" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["trip_id"] == 42
    assert manifest["status"] == "PARTIAL"
    assert manifest["dropped_record_count"] >= 1


def test_camera_listener_uses_same_client_and_monotonic_sequence(tmp_path):
    if not CV2_AVAILABLE:
        return
    recorder = CameraLidarDiagnosticRecorder(enabled=True, base_dir=tmp_path)
    camera = CameraClient()
    recorder.attach_camera(camera)
    recorder.start("camera", started_at="2026-08-09T00:00:00+00:00")
    camera._publish_frame(np.zeros((10, 10, 3), dtype=np.uint8))
    camera._publish_frame(np.zeros((10, 10, 3), dtype=np.uint8))
    recorder.stop()
    rows = (tmp_path / "camera" / "camera" / "frames.csv").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 3
    assert camera._capture_thread is None
    with (tmp_path / "camera" / "camera" / "frames.csv").open(encoding="utf-8", newline="") as handle:
        samples = list(csv.DictReader(handle))
    assert int(samples[1]["captured_monotonic_ns"]) > int(samples[0]["captured_monotonic_ns"])


def test_enqueue_path_is_non_blocking_under_normal_synthetic_load(tmp_path):
    recorder = CameraLidarDiagnosticRecorder(enabled=True, base_dir=tmp_path, queue_size=1000)
    recorder.start("throughput", started_at="2026-08-09T00:00:00+00:00")
    started = time.perf_counter()
    for sequence in range(500):
        recorder.record_lidar({
            "sequence_number": sequence,
            "captured_monotonic_ns": time.monotonic_ns(),
            "ranges_raw": [1000] * 32,
        })
    enqueue_seconds = time.perf_counter() - started
    recorder.stop()
    assert enqueue_seconds < 0.5
    manifest = json.loads((tmp_path / "throughput" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["record_counts"]["lidar"] == 500


def test_nearest_matching_and_analyzer(tmp_path):
    session = tmp_path / "s"
    (session / "lidar").mkdir(parents=True); (session / "camera").mkdir()
    (session / "manifest.json").write_text(json.dumps({"format_version": 2, "session_key": "s", "status": "COMPLETED"}), encoding="utf-8")
    (session / "lidar" / "raw_scans.jsonl").write_text(json.dumps({"sequence_number": 1, "captured_utc": "x", "captured_monotonic_ns": 1_100_000_000, "acquisition_latency_ms": 300}) + "\n", encoding="utf-8")
    (session / "camera" / "frames.csv").write_text("sequence_number,captured_monotonic_ns,captured_utc\n2,1000000000,x\n3,2000000000,y\n", encoding="utf-8")
    summary, tables = analyze_session(session)
    assert tables["matches"][0]["camera_sequence"] == "2"
    assert tables["matches"][0]["delta_ms"] == -100.0
    assert summary["lidar"]["latency_ms_median"] == 300.0
