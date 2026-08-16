import json
import threading
import time

from scripts.validate_diagnostic_vehicle_binding import validate_manifest
from services.camera_lidar_diagnostic_recorder import CameraLidarDiagnosticRecorder


IDENTITY_A = dict(
    trip_id=100, vehicle_id=10, license_plate_snapshot="A100AA",
    uniserver_code="DOC-100", pass_token="session-a",
)


def manifest(root, key):
    return json.loads((root / key / "manifest.json").read_text(encoding="utf-8"))


def test_single_trip_manifest_has_self_contained_identity(tmp_path):
    recorder = CameraLidarDiagnosticRecorder(enabled=True, base_dir=tmp_path)
    recorder.start("session-a", started_at="2026-08-16T00:00:00+00:00")
    assert recorder.bind_trip(**IDENTITY_A)
    recorder.record_lidar({"sequence_number": 1, "captured_monotonic_ns": time.monotonic_ns()})
    recorder.stop(reason="TEST")
    saved = manifest(tmp_path, "session-a")
    assert saved["identity_binding_version"] == 1
    assert saved["trip_id"] == 100
    assert saved["vehicle_id"] == 10
    assert saved["license_plate_snapshot"] == "A100AA"
    assert saved["uniserver_code"] == "DOC-100"
    assert saved["identity"] == saved["bindings"][0]
    assert saved["finalize_reason"] == "TEST"


def test_repeated_same_bind_is_idempotent(tmp_path):
    recorder = CameraLidarDiagnosticRecorder(enabled=True, base_dir=tmp_path)
    recorder.start("session-a", started_at="x")
    assert recorder.bind_trip(**IDENTITY_A)
    assert recorder.bind_trip(**IDENTITY_A)
    recorder.stop()
    saved = manifest(tmp_path, "session-a")
    assert len(saved["bindings"]) == 1
    events = (tmp_path / "session-a" / "events.jsonl").read_text(encoding="utf-8")
    assert events.count('"event":"TRIP_BOUND"') == 1


def test_different_trip_rebind_is_rejected_without_history_rewrite(tmp_path):
    recorder = CameraLidarDiagnosticRecorder(enabled=True, base_dir=tmp_path)
    recorder.start("session-a", started_at="x")
    assert recorder.bind_trip(**IDENTITY_A)
    assert not recorder.bind_trip(
        trip_id=101, vehicle_id=11, license_plate_snapshot="B101BB",
        uniserver_code="DOC-101", pass_token="session-a",
    )
    recorder.stop()
    assert [row["trip_id"] for row in manifest(tmp_path, "session-a")["bindings"]] == [100]


def test_new_session_during_grace_rolls_over_and_separates_samples(tmp_path):
    recorder = CameraLidarDiagnosticRecorder(
        enabled=True, base_dir=tmp_path, extended_session=True, post_finalize_grace_sec=60,
    )
    recorder.start("session-a", started_at="x")
    recorder.bind_trip(**IDENTITY_A)
    recorder.record_lidar({"sequence_number": 1, "captured_monotonic_ns": 1})
    recorder.production_finalized(ended_at="2026-08-16T00:00:01+00:00")
    recorder.start("session-b", started_at="y")
    recorder.bind_trip(
        trip_id=101, vehicle_id=11, license_plate_snapshot="B101BB",
        uniserver_code="DOC-101", pass_token="session-b",
    )
    recorder.record_lidar({"sequence_number": 2, "captured_monotonic_ns": 2})
    recorder.stop()
    old, new = manifest(tmp_path, "session-a"), manifest(tmp_path, "session-b")
    assert old["finalize_reason"] == "NEXT_TRIP_STARTED"
    assert old["trip_id"] == 100 and new["trip_id"] == 101
    assert old["record_counts"]["lidar"] == new["record_counts"]["lidar"] == 1
    assert '"sequence_number":1' in (tmp_path / "session-a" / "lidar" / "raw_scans.jsonl").read_text()
    assert '"sequence_number":2' in (tmp_path / "session-b" / "lidar" / "raw_scans.jsonl").read_text()


def test_same_session_start_during_grace_keeps_extended_recording(tmp_path):
    recorder = CameraLidarDiagnosticRecorder(enabled=True, base_dir=tmp_path, extended_session=True)
    recorder.start("session-a", started_at="x")
    recorder.bind_trip(**IDENTITY_A)
    recorder.production_finalized(ended_at="x")
    recorder.start("session-a", started_at="x")
    recorder.record_lidar({"sequence_number": 1, "captured_monotonic_ns": 1})
    recorder.stop()
    assert manifest(tmp_path, "session-a")["record_counts"]["lidar"] == 1


def test_same_vehicle_new_trip_still_creates_new_diagnostic_session(tmp_path):
    recorder = CameraLidarDiagnosticRecorder(enabled=True, base_dir=tmp_path, extended_session=True)
    recorder.start("session-a", started_at="x")
    recorder.bind_trip(**IDENTITY_A)
    recorder.production_finalized(ended_at="x")
    recorder.start("session-b", started_at="y")
    recorder.bind_trip(
        trip_id=101, vehicle_id=10, license_plate_snapshot="A100AA",
        uniserver_code="DOC-101", pass_token="session-b",
    )
    recorder.stop()
    assert manifest(tmp_path, "session-a")["trip_id"] == 100
    assert manifest(tmp_path, "session-b")["trip_id"] == 101
    assert manifest(tmp_path, "session-a")["vehicle_id"] == 10
    assert manifest(tmp_path, "session-b")["vehicle_id"] == 10


def test_missing_plate_snapshot_does_not_prevent_trip_vehicle_binding(tmp_path):
    recorder = CameraLidarDiagnosticRecorder(enabled=True, base_dir=tmp_path)
    recorder.start("session-a", started_at="x")
    assert recorder.bind_trip(
        trip_id=100, vehicle_id=10, license_plate_snapshot=None,
        uniserver_code="DOC-100", pass_token="session-a",
    )
    recorder.stop()
    saved = manifest(tmp_path, "session-a")
    assert saved["trip_id"] == 100 and saved["vehicle_id"] == 10
    assert saved["license_plate_snapshot"] is None
    assert validate_manifest(tmp_path / "session-a" / "manifest.json")["identity_status"] == "INCOMPLETE_IDENTITY"


def test_concurrent_callbacks_do_not_duplicate_across_rollover(tmp_path):
    recorder = CameraLidarDiagnosticRecorder(enabled=True, base_dir=tmp_path, queue_size=2000)
    recorder.start("session-a", started_at="x")
    recorder.bind_trip(**IDENTITY_A)
    running = threading.Event(); running.set()

    def producer():
        sequence = 0
        while running.is_set():
            recorder.record_lidar({"sequence_number": sequence, "captured_monotonic_ns": sequence})
            sequence += 1

    thread = threading.Thread(target=producer)
    thread.start()
    time.sleep(0.01)
    recorder.start("session-b", started_at="y")
    recorder.bind_trip(trip_id=101, vehicle_id=11, license_plate_snapshot="B", pass_token="session-b")
    time.sleep(0.01)
    running.clear(); thread.join(timeout=1); recorder.stop()
    old_lines = (tmp_path / "session-a" / "lidar" / "raw_scans.jsonl").read_text().splitlines()
    new_lines = (tmp_path / "session-b" / "lidar" / "raw_scans.jsonl").read_text().splitlines()
    old_ids = {json.loads(line)["sequence_number"] for line in old_lines}
    new_ids = {json.loads(line)["sequence_number"] for line in new_lines}
    assert old_ids.isdisjoint(new_ids)


def test_validator_classifies_new_legacy_and_invalid_manifests(tmp_path):
    valid = tmp_path / "valid.json"
    valid.write_text(json.dumps({"session_key": "s", "bindings": [IDENTITY_A], "identity": IDENTITY_A}))
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps({"session_key": "old", "trip_id": 1}))
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({"session_key": "bad", "bindings": [{"trip_id": 1}, {"trip_id": 2}]}))
    assert validate_manifest(valid)["identity_status"] == "VALID_SINGLE_TRIP"
    assert validate_manifest(legacy)["identity_status"] == "LEGACY_NO_IDENTITY"
    assert validate_manifest(invalid)["identity_status"] == "INVALID_MULTI_TRIP"
