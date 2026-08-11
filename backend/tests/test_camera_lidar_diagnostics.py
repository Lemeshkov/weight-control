import csv
import asyncio
import importlib
import json
import time
from pathlib import Path

import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scripts.analyze_camera_lidar_session import analyze_session, nearest_matches
from services.camera_client import CV2_AVAILABLE, CameraClient
from services.camera_lidar_diagnostic_recorder import CameraLidarDiagnosticRecorder
from services.lidar_client import LidarClient
from services.lidar_profile_buffer import LidarProfileBuffer
from services.lidar_pass_storage import AtomicLidarPassStorage
from services.lidar_session_repository import InMemoryLidarSessionRepository
from routers import camera as camera_router


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
    assert parsed["native_scan_frequency_hz"] is None
    assert parsed["measurement_frequency_hz"] is None


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
    recorder = CameraLidarDiagnosticRecorder(enabled=True, base_dir=tmp_path, camera_max_fps=0)
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
    assert all(int(row["writer_persisted_monotonic_ns"]) >= int(row["recorder_observed_monotonic_ns"]) for row in samples)


def test_duplicate_camera_sequence_is_not_written_twice(tmp_path):
    recorder = CameraLidarDiagnosticRecorder(enabled=True, base_dir=tmp_path)
    recorder.start("duplicate", started_at="2026-08-10T00:00:00+00:00")
    sample = {
        "sequence_number": 7, "captured_utc": "2026-08-10T00:00:00+00:00",
        "captured_monotonic_ns": 7, "jpeg": b"jpeg", "width": 10, "height": 10,
    }
    recorder.record_camera(sample)
    recorder.record_camera(sample)
    recorder.stop()
    manifest = json.loads((tmp_path / "duplicate" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["record_counts"]["camera"] == 1
    assert manifest["camera_duplicate_sequence_count"] == 1
    assert len(list((tmp_path / "duplicate" / "camera").glob("*.jpg"))) == 1


def test_diagnostic_camera_sampling_does_not_limit_producer(tmp_path):
    recorder = CameraLidarDiagnosticRecorder(enabled=True, base_dir=tmp_path, camera_max_fps=5)
    recorder.start("sampled", started_at="2026-08-10T00:00:00+00:00")
    for sequence, captured_ns in enumerate((1_000_000_000, 1_100_000_000, 1_200_000_000), start=1):
        recorder.record_camera({
            "sequence_number": sequence, "captured_utc": "2026-08-10T00:00:00+00:00",
            "captured_monotonic_ns": captured_ns, "jpeg": b"jpeg", "width": 10, "height": 10,
        })
    recorder.stop()
    manifest = json.loads((tmp_path / "sampled" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["record_counts"]["camera"] == 2
    assert manifest["camera_sampled_out_count"] == 1


def test_camera_enqueue_does_not_wait_for_writer_disk_io(tmp_path):
    recorder = CameraLidarDiagnosticRecorder(enabled=True, base_dir=tmp_path, queue_size=500, camera_max_fps=0)
    recorder.start("camera_queue", started_at="2026-08-10T00:00:00+00:00")
    started = time.perf_counter()
    for sequence in range(100):
        recorder.record_camera({
            "sequence_number": sequence, "captured_utc": "2026-08-10T00:00:00+00:00",
            "captured_monotonic_ns": sequence, "jpeg": b"jpeg", "width": 10, "height": 10,
        })
    enqueue_seconds = time.perf_counter() - started
    recorder.stop()
    assert enqueue_seconds < 0.5
    manifest = json.loads((tmp_path / "camera_queue" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["record_counts"]["camera"] == 100


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


def test_all_actual_event_producers_share_one_contract(tmp_path):
    recorder = CameraLidarDiagnosticRecorder(enabled=True, base_dir=tmp_path)
    recorder.start("events", started_at="2026-08-10T07:02:43+00:00")
    recorder.record_event("SESSION_OPENED", scale_state="LoadScale", weight_kg=100, stable=False)
    recorder.record_event("SCALE_SNAPSHOT", scale_state="Weighing", weight_kg=1000, stable=True, state_changed=True)
    recorder.record_event("COORDINATOR_TRANSITION", workflow_state="WEIGHING", scale_state="Weighing")
    recorder.record_event("STABLE_WEIGHT", workflow_state="WEIGHT_CAPTURED", weight_kg=1000, stable_samples=3)
    recorder.bind_trip(13)
    recorder.record_event("SESSION_FINALIZED", coordinator_status="COMPLETED", workflow_state="COMPLETED")
    recorder.stop()

    session = tmp_path / "events"
    records = [json.loads(line) for line in (session / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [record["event"] for record in records] == [
        "SESSION_OPENED", "SCALE_SNAPSHOT", "COORDINATOR_TRANSITION",
        "STABLE_WEIGHT", "TRIP_BOUND", "SESSION_FINALIZED",
    ]
    assert all(set(record) == {"type", "event", "captured_utc", "captured_monotonic_ns", "payload"} for record in records)
    manifest = json.loads((session / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["record_counts"]["events"] == 6
    assert manifest["status"] == "COMPLETED"
    assert manifest["errors"] == []


def test_active_marker_endpoint_writes_marker_contract(tmp_path, monkeypatch):
    recorder = CameraLidarDiagnosticRecorder(enabled=True, base_dir=tmp_path)
    recorder.start("marker", started_at="2026-08-10T07:02:43+00:00")
    monkeypatch.setattr(camera_router, "diagnostic_recorder", recorder)
    app = FastAPI()
    app.include_router(camera_router.router)

    response = TestClient(app).post("/api/camera/debug/diagnostics/marker", json={"label": "STOPPED"})
    assert response.status_code == 200
    recorder.stop()

    session = tmp_path / "marker"
    records = [json.loads(line) for line in (session / "markers.jsonl").read_text(encoding="utf-8").splitlines()]
    assert records == [{
        "type": "marker", "event": "OPERATOR_MARKER",
        "session_key": "marker",
        "captured_utc": records[0]["captured_utc"],
        "captured_monotonic_ns": records[0]["captured_monotonic_ns"],
        "payload": {"label": "STOPPED"},
    }]
    manifest = json.loads((session / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["record_counts"]["markers"] == 1
    assert manifest["status"] == "COMPLETED"


def test_vehicle_presence_markers_are_accepted_and_persisted(tmp_path, monkeypatch):
    recorder = CameraLidarDiagnosticRecorder(enabled=True, base_dir=tmp_path)
    recorder.start("presence", started_at="2026-08-11T07:00:00+00:00")
    monkeypatch.setattr(camera_router, "diagnostic_recorder", recorder)
    app = FastAPI(); app.include_router(camera_router.router)
    client = TestClient(app)

    for label in ("VEHICLE_ENTERED", "VEHICLE_EXITED"):
        response = client.post("/api/camera/debug/diagnostics/marker", json={"label": label})
        assert response.status_code == 200
        assert response.json() == {"recorded": True, "label": label}
    assert client.post("/api/camera/debug/diagnostics/marker", json={"label": "NOT_A_MARKER"}).status_code == 409
    recorder.stop()

    records = [json.loads(line) for line in (tmp_path / "presence" / "markers.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [row["payload"]["label"] for row in records] == ["VEHICLE_ENTERED", "VEHICLE_EXITED"]
    assert all(row["session_key"] == "presence" for row in records)
    assert all(row["captured_utc"] and isinstance(row["captured_monotonic_ns"], int) for row in records)


def test_marker_endpoint_rejects_after_session_finished(tmp_path, monkeypatch):
    recorder = CameraLidarDiagnosticRecorder(enabled=True, base_dir=tmp_path)
    recorder.start("ended", started_at="2026-08-10T07:02:43+00:00")
    recorder.stop()
    monkeypatch.setattr(camera_router, "diagnostic_recorder", recorder)
    app = FastAPI(); app.include_router(camera_router.router)

    response = TestClient(app).post("/api/camera/debug/diagnostics/marker", json={"label": "STOPPED"})
    assert response.status_code == 409


def test_extended_diagnostic_survives_production_finalize_until_explicit_finish(tmp_path, monkeypatch):
    recorder = CameraLidarDiagnosticRecorder(
        enabled=True,
        base_dir=tmp_path,
        camera_max_fps=0,
        extended_session=True,
        post_finalize_grace_sec=60,
    )
    recorder.start("same-session-key", started_at="2026-08-10T07:02:43+00:00", trip_id=13)
    recorder.record_event("SESSION_OPENED", scale_state="LoadScale")
    recorder.record_event("SESSION_FINALIZED", coordinator_status="COMPLETED")
    recorder.production_finalized(ended_at="2026-08-10T07:02:56+00:00")

    monkeypatch.setattr(camera_router, "diagnostic_recorder", recorder)
    app = FastAPI(); app.include_router(camera_router.router)
    client = TestClient(app)

    status = client.get("/api/camera/debug/diagnostics/status")
    assert status.status_code == 200
    assert status.json()["diagnostic_active"] is True
    assert status.json()["session_key"] == "same-session-key"
    assert client.post("/api/camera/debug/diagnostics/marker", json={"label": "STOPPED"}).status_code == 200

    recorder.record_lidar({
        "format_version": 2,
        "sequence_number": 101,
        "captured_monotonic_ns": time.monotonic_ns(),
        "ranges_raw": [1000, 1001],
    })
    recorder.record_camera({
        "sequence_number": 202,
        "captured_utc": "2026-08-10T07:03:00+00:00",
        "captured_monotonic_ns": time.monotonic_ns(),
        "jpeg": b"jpeg-after-production-finalize",
        "width": 10,
        "height": 10,
    })
    recorder.record_event("SCALE_SNAPSHOT", scale_state="Empty", weight_kg=0, stable=True)
    assert client.post("/api/camera/debug/diagnostics/marker", json={"label": "RESUMED"}).status_code == 200
    finish = client.post("/api/camera/debug/diagnostics/finish")
    assert finish.status_code == 200
    assert finish.json()["diagnostic_active"] is False
    assert client.post("/api/camera/debug/diagnostics/marker", json={"label": "STOPPED"}).status_code == 409

    session = tmp_path / "same-session-key"
    manifest = json.loads((session / "manifest.json").read_text(encoding="utf-8"))
    markers = [json.loads(line) for line in (session / "markers.jsonl").read_text(encoding="utf-8").splitlines()]
    lidar = (session / "lidar" / "raw_scans.jsonl").read_text(encoding="utf-8").splitlines()
    frames = list((session / "camera").glob("*.jpg"))
    assert manifest["status"] == "COMPLETED"
    assert manifest["session_key"] == "same-session-key"
    assert manifest["record_counts"]["markers"] == 2
    assert manifest["record_counts"]["lidar"] == 1
    assert manifest["record_counts"]["camera"] == 1
    assert manifest["errors"] == []
    assert manifest["diagnostic_lifecycle"]["finish_reason"] == "EXPLICIT_FINISH"
    assert [item["payload"]["label"] for item in markers] == ["STOPPED", "RESUMED"]
    assert len(lidar) == 1
    assert len(frames) == 1


def test_extended_diagnostic_finishes_after_grace_timeout(tmp_path):
    recorder = CameraLidarDiagnosticRecorder(
        enabled=True,
        base_dir=tmp_path,
        extended_session=True,
        post_finalize_grace_sec=0.02,
    )
    recorder.start("timeout", started_at="2026-08-10T07:02:43+00:00")
    recorder.production_finalized(ended_at="2026-08-10T07:02:56+00:00")
    deadline = time.time() + 2
    while recorder.active and time.time() < deadline:
        time.sleep(0.01)

    assert recorder.active is False
    assert recorder.marker("STOPPED") is False
    manifest = json.loads((tmp_path / "timeout" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETED"
    assert manifest["diagnostic_lifecycle"]["finish_reason"] == "POST_FINALIZE_GRACE_TIMEOUT"


def test_non_extended_diagnostic_still_finishes_with_production_session(tmp_path):
    recorder = CameraLidarDiagnosticRecorder(enabled=True, base_dir=tmp_path, extended_session=False)
    recorder.start("normal", started_at="2026-08-10T07:02:43+00:00")
    recorder.production_finalized(ended_at="2026-08-10T07:02:56+00:00")
    deadline = time.time() + 2
    while recorder.active and time.time() < deadline:
        time.sleep(0.01)

    assert recorder.active is False
    manifest = json.loads((tmp_path / "normal" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["diagnostic_lifecycle"]["finish_reason"] == "PRODUCTION_FINALIZED"


def test_coordinator_finalize_leaves_extended_recorder_and_scale_timeline_active(tmp_path, monkeypatch):
    module = importlib.import_module("services.weighing_lidar_coordinator")
    recorder = CameraLidarDiagnosticRecorder(
        enabled=True, base_dir=tmp_path / "diagnostics",
        extended_session=True, post_finalize_grace_sec=60,
    )
    monkeypatch.setattr(module, "diagnostic_recorder", recorder)

    class ConnectedClient:
        is_connected = True

    buffer = LidarProfileBuffer(client=ConnectedClient(), buffer_seconds=5, max_count=10)
    buffer.add_profile([1000], captured_at=module.utc_now())
    coordinator = module.WeighingLidarCoordinator(
        buffer=buffer,
        repository=InMemoryLidarSessionRepository(),
        storage=AtomicLidarPassStorage(str(tmp_path / "passes")),
        stable_confirm_samples=1,
        post_stable_seconds=0,
    )

    def scale(state, weight, stable):
        return {"full_response": {"StateName": state, "Massa": weight, "Stabil": stable}}

    async def scenario():
        await coordinator.on_scale_snapshot(scale("LoadScale", 500, False))
        session_key = coordinator.active_session.session_key
        await coordinator.on_scale_snapshot(scale("Weighing", 1500, True))
        await coordinator._finish_task
        assert coordinator.active_session is None
        assert recorder.active is True
        await coordinator.on_scale_snapshot(scale("Empty", 0, True))
        return session_key

    session_key = asyncio.run(scenario())
    recorder.finish()

    session = tmp_path / "diagnostics" / session_key
    events = [json.loads(line) for line in (session / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(
        item["event"] == "SCALE_SNAPSHOT" and item["payload"]["scale_state"] == "Empty"
        for item in events
    )
