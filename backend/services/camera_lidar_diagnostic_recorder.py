from __future__ import annotations

import csv
import hashlib
import json
import logging
import queue
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config import settings

logger = logging.getLogger(__name__)

DIAGNOSTIC_MARKER_LABELS = {
    "MOVING", "STOPPED", "RESUMED", "VEHICLE_ENTERED", "VEHICLE_EXITED",
}


class CameraLidarDiagnosticRecorder:
    """Non-blocking, opt-in writer for one physical pass."""

    def __init__(self, *, enabled=None, base_dir=None, queue_size=None, max_duration_sec=None, max_bytes=None,
                 camera_max_fps=None, side_camera_max_fps=None, extended_session=None, post_finalize_grace_sec=None):
        self.enabled = settings.CAMERA_LIDAR_DIAGNOSTIC_RECORDING if enabled is None else enabled
        self.base_dir = Path(base_dir or settings.DIAGNOSTIC_DATA_DIR)
        self.queue_size = queue_size or settings.DIAGNOSTIC_QUEUE_SIZE
        self.max_duration_sec = max_duration_sec or settings.DIAGNOSTIC_MAX_DURATION_SEC
        self.max_bytes = max_bytes or settings.DIAGNOSTIC_MAX_BYTES
        self.camera_max_fps = settings.DIAGNOSTIC_CAMERA_MAX_FPS if camera_max_fps is None else camera_max_fps
        self.side_camera_max_fps = settings.DIAGNOSTIC_SIDE_CAMERA_MAX_FPS if side_camera_max_fps is None else side_camera_max_fps
        self.extended_session = (
            settings.CAMERA_LIDAR_DIAGNOSTIC_EXTENDED_SESSION
            if extended_session is None else extended_session
        )
        self.post_finalize_grace_sec = (
            settings.DIAGNOSTIC_POST_FINALIZE_GRACE_SEC
            if post_finalize_grace_sec is None else post_finalize_grace_sec
        )
        self._queue: queue.Queue = queue.Queue(maxsize=self.queue_size)
        self._thread: threading.Thread | None = None
        self._session_dir: Path | None = None
        self._manifest: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._stop_lock = threading.Lock()
        self._bytes_written = 0
        self._camera_sequences_seen: set[int] = set()
        self._last_camera_recorded_monotonic_ns: Optional[int] = None
        self._side_camera_sequences_seen: set[int] = set()
        self._last_side_camera_recorded_monotonic_ns: Optional[int] = None
        self._side_camera_times: list[int] = []
        self._side_camera_bytes = 0
        self._side_camera_service = None
        self._finish_timer: Optional[threading.Timer] = None
        self._production_finalized_monotonic_ns: Optional[int] = None
        self._accepting = False
        self._rollover_from: dict[str, Any] | None = None

    @property
    def active(self) -> bool:
        return self._session_dir is not None

    def attach_camera(self, camera_client) -> None:
        camera_client.add_frame_listener(self.record_camera)

    def attach_side_camera(self, side_camera_service) -> None:
        """Subscribe only to the optional producer; never starts or requires it."""
        self._side_camera_service = side_camera_service
        side_camera_service.add_frame_listener(self.record_side_camera)

    @staticmethod
    def _git_commit() -> str | None:
        try:
            return subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=1, check=True
            ).stdout.strip()
        except Exception:
            return None

    def start(self, session_key: str, *, started_at: str, trip_id=None, camera_config=None) -> None:
        if not self.enabled:
            return
        with self._stop_lock:
            if self.active and self._manifest.get("session_key") == session_key:
                return
            rollover_from = None
            if self.active:
                rollover_from = {
                    "old_session_key": self._manifest.get("session_key"),
                    "old_trip_id": self._manifest.get("trip_id"),
                    "new_session_key": session_key,
                    "reason": "NEXT_TRIP_STARTED",
                }
                self.record_event(
                    "DIAGNOSTIC_SESSION_ROLLOVER",
                    **rollover_from,
                    new_trip_id=None,
                )
                self._stop_locked(reason="NEXT_TRIP_STARTED")
        session_dir = self.base_dir / session_key
        self._session_dir = session_dir
        self._queue = queue.Queue(maxsize=self.queue_size)
        self._bytes_written = 0
        self._camera_sequences_seen = set()
        self._last_camera_recorded_monotonic_ns = None
        self._side_camera_sequences_seen = set()
        self._last_side_camera_recorded_monotonic_ns = None
        self._side_camera_times = []
        self._side_camera_bytes = 0
        self._production_finalized_monotonic_ns = None
        self._manifest = {
            "format_version": 2, "identity_binding_version": 1,
            "status": "RECORDING", "session_key": session_key,
            "trip_id": trip_id, "vehicle_id": None, "license_plate_snapshot": None,
            "uniserver_code": None, "identity": None, "bindings": [],
            "started_at": started_at, "started_at_utc": started_at,
            "started_monotonic_ns": time.monotonic_ns(),
            "software_git_commit": None, "camera_configuration": camera_config or {},
            "lidar_configuration": {"source": "per-profile LMDscandata.DIST1"},
            "record_counts": {"lidar": 0, "camera": 0, "camera_side": 0, "events": 0, "markers": 0},
            "camera_duplicate_sequence_count": 0,
            "camera_sampled_out_count": 0,
            "side_camera_configuration": self._safe_side_camera_configuration(),
            "side_camera_statistics": {
                "frames_received": 0, "frames_saved": 0, "first_monotonic_ns": None,
                "last_monotonic_ns": None, "median_frame_interval_ms": None,
                "p95_frame_interval_ms": None, "max_frame_interval_ms": None,
                "capture_gaps_count": 0,
                "bytes_saved": 0, "average_jpeg_bytes": None,
                "estimated_disk_mb_per_minute": None, "estimated_disk_gb_per_hour": None,
            },
            "side_camera_duplicate_sequence_count": 0,
            "side_camera_sampled_out_count": 0,
            "diagnostic_lifecycle": {
                "extended_session": self.extended_session,
                "production_finalized_at": None,
                "finish_reason": None,
                "rollover_from": rollover_from,
            },
            "dropped_record_count": 0, "errors": [],
            "limits": {
                "max_duration_sec": self.max_duration_sec,
                "max_bytes": self.max_bytes,
                "queue_size": self.queue_size,
                "camera_max_fps": self.camera_max_fps,
                "side_camera_max_fps": self.side_camera_max_fps,
            },
        }
        self._accepting = True
        self._rollover_from = rollover_from
        self._thread = threading.Thread(target=self._writer_loop, name="diagnostic-writer", daemon=True)
        self._thread.start()

    def _enqueue(self, kind: str, payload: dict) -> None:
        if not self.active or not self._accepting:
            return
        elapsed = (time.monotonic_ns() - self._manifest["started_monotonic_ns"]) / 1e9
        if elapsed > self.max_duration_sec or self._bytes_written >= self.max_bytes:
            self._manifest["status"] = "PARTIAL"
            self._manifest["limit_reached"] = "duration" if elapsed > self.max_duration_sec else "bytes"
            self._manifest["dropped_record_count"] += 1
            return
        try:
            self._queue.put_nowait((kind, payload))
        except queue.Full:
            self._manifest["status"] = "PARTIAL"
            self._manifest["dropped_record_count"] += 1
            logger.warning("Diagnostic writer queue full; %s record dropped", kind)

    def record_camera(self, sample: dict) -> None:
        if not self.active or not self._accepting:
            return
        sequence = int(sample["sequence_number"])
        with self._lock:
            if sequence in self._camera_sequences_seen:
                self._manifest["camera_duplicate_sequence_count"] += 1
                return
            self._camera_sequences_seen.add(sequence)
            captured_ns = int(sample["captured_monotonic_ns"])
            minimum_interval_ns = int(1_000_000_000 / self.camera_max_fps) if self.camera_max_fps > 0 else 0
            if (
                minimum_interval_ns
                and self._last_camera_recorded_monotonic_ns is not None
                and captured_ns - self._last_camera_recorded_monotonic_ns < minimum_interval_ns
            ):
                self._manifest["camera_sampled_out_count"] += 1
                return
            self._last_camera_recorded_monotonic_ns = captured_ns
        payload = dict(sample)
        payload["recorder_observed_monotonic_ns"] = time.monotonic_ns()
        self._enqueue("camera", payload)

    def _safe_side_camera_configuration(self) -> dict:
        status = self._side_camera_service.status() if self._side_camera_service else {}
        return {
            "camera_source": "SIDE_CAMERA", "enabled": bool(status.get("enabled")),
            "configured_host": status.get("configured_host"), "stream_type": status.get("stream_type", "UNIDENTIFIED"),
            "resolution": status.get("resolution"), "reported_fps": status.get("measured_fps"),
            "target_recording_fps": self.side_camera_max_fps,
        }

    def record_side_camera(self, sample: dict) -> None:
        """Best-effort side frame recording, isolated from production capture."""
        if not self.active or not self._accepting:
            return
        try:
            sequence = int(sample.get("frame_counter", sample["sequence_number"]))
            captured_ns = int(sample.get("receive_monotonic_ns", sample["captured_monotonic_ns"]))
            with self._lock:
                stats = self._manifest["side_camera_statistics"]
                stats["frames_received"] += 1
                if sequence in self._side_camera_sequences_seen:
                    self._manifest["side_camera_duplicate_sequence_count"] += 1
                    return
                self._side_camera_sequences_seen.add(sequence)
                minimum_ns = int(1_000_000_000 / self.side_camera_max_fps) if self.side_camera_max_fps > 0 else 0
                if minimum_ns and self._last_side_camera_recorded_monotonic_ns is not None and captured_ns - self._last_side_camera_recorded_monotonic_ns < minimum_ns:
                    self._manifest["side_camera_sampled_out_count"] += 1
                    return
                self._last_side_camera_recorded_monotonic_ns = captured_ns
                self._side_camera_times.append(captured_ns)
            payload = dict(sample)
            payload["captured_monotonic_ns"] = captured_ns
            payload["camera_source"] = "SIDE_CAMERA"
            payload["recorder_observed_monotonic_ns"] = time.monotonic_ns()
            self._enqueue("camera_side", payload)
        except Exception as exc:
            logger.warning("SIDE_CAMERA diagnostic frame rejected: %s", type(exc).__name__)

    def record_lidar(self, sample: dict) -> None:
        if self.active and self._accepting and self._manifest["lidar_configuration"].get("beam_count") is None:
            self._manifest["lidar_configuration"].update({
                key: sample.get(key) for key in (
                    "native_scan_frequency_hz", "measurement_frequency_hz", "start_angle_deg",
                    "end_angle_deg", "angular_step_deg", "beam_count", "scale_factor_raw", "scale_offset_raw",
                )
            })
        self._enqueue("lidar", dict(sample))

    def record_event(self, event_type: str, **values) -> None:
        self._enqueue("events", {
            "type": "event",
            "event": event_type,
            "captured_utc": datetime.now(timezone.utc).isoformat(),
            "captured_monotonic_ns": time.monotonic_ns(),
            "payload": values,
        })

    def bind_trip(
        self,
        trip_id: int,
        *,
        vehicle_id: int | None = None,
        license_plate_snapshot: str | None = None,
        uniserver_code: str | None = None,
        pass_token: str | None = None,
    ) -> bool:
        if not self.active:
            return False
        existing = self._manifest.get("identity")
        if existing is not None:
            same_binding = (
                existing.get("trip_id") == trip_id
                and existing.get("pass_token") == pass_token
            )
            if not same_binding:
                logger.error(
                    "Diagnostic identity rebind rejected: session=%s existing_trip_id=%s requested_trip_id=%s",
                    self._manifest.get("session_key"), existing.get("trip_id"), trip_id,
                )
            return same_binding

        bound_at_utc = datetime.now(timezone.utc).isoformat()
        bound_at_monotonic_ns = time.monotonic_ns()
        binding = {
            "session_key": self._manifest["session_key"],
            "trip_id": trip_id,
            "vehicle_id": vehicle_id,
            "license_plate_snapshot": license_plate_snapshot,
            "uniserver_code": uniserver_code,
            "bound_at_utc": bound_at_utc,
            "bound_at_monotonic_ns": bound_at_monotonic_ns,
            "pass_token": pass_token,
        }
        self._manifest.update({
            "trip_id": trip_id,
            "vehicle_id": vehicle_id,
            "license_plate_snapshot": license_plate_snapshot,
            "uniserver_code": uniserver_code,
            "identity": dict(binding),
        })
        self._manifest["bindings"].append(dict(binding))
        self.record_event("TRIP_BOUND", **binding)
        if self._rollover_from is not None:
            self.record_event(
                "DIAGNOSTIC_SESSION_ROLLOVER",
                **self._rollover_from,
                new_trip_id=trip_id,
            )
            self._rollover_from = None
        return True

    def marker(self, label: str) -> bool:
        if label not in DIAGNOSTIC_MARKER_LABELS or not self.active:
            return False
        self._enqueue("markers", {
            "type": "marker",
            "event": "OPERATOR_MARKER",
            "session_key": self._manifest["session_key"],
            "captured_utc": datetime.now(timezone.utc).isoformat(),
            "captured_monotonic_ns": time.monotonic_ns(),
            "payload": {"label": label},
        })
        return True

    def production_finalized(self, *, ended_at: str | None = None) -> None:
        """React to production finalization without changing production lifecycle."""
        if not self.active:
            return
        finalized_at = ended_at or datetime.now(timezone.utc).isoformat()
        self._manifest["diagnostic_lifecycle"]["production_finalized_at"] = finalized_at
        self._production_finalized_monotonic_ns = time.monotonic_ns()
        if not self.extended_session:
            self.stop_in_background(ended_at=finalized_at, reason="PRODUCTION_FINALIZED")
            return
        self.record_event(
            "DIAGNOSTIC_GRACE_STARTED",
            grace_seconds=self.post_finalize_grace_sec,
            production_finalized_at=finalized_at,
        )
        if self._finish_timer:
            self._finish_timer.cancel()
        self._finish_timer = threading.Timer(
            self.post_finalize_grace_sec,
            self.stop,
            kwargs={"reason": "POST_FINALIZE_GRACE_TIMEOUT"},
        )
        self._finish_timer.daemon = True
        self._finish_timer.start()

    def status(self) -> dict:
        remaining = None
        if self.active and self._production_finalized_monotonic_ns is not None:
            elapsed = (time.monotonic_ns() - self._production_finalized_monotonic_ns) / 1e9
            remaining = max(0.0, self.post_finalize_grace_sec - elapsed)
        return {
            "diagnostic_active": self.active,
            "session_key": self._manifest.get("session_key") if self.active else None,
            "extended_session": self.extended_session,
            "production_finalized_at": self._manifest.get("diagnostic_lifecycle", {}).get("production_finalized_at"),
            "grace_remaining_sec": round(remaining, 3) if remaining is not None else None,
        }

    def finish(self) -> bool:
        if not self.active:
            return False
        self.stop(reason="EXPLICIT_FINISH")
        return True

    def _append_jsonl(self, relative: str, payload: dict) -> None:
        encoded = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        with (self._session_dir / relative).open("ab") as handle:
            handle.write(encoded)
        self._bytes_written += len(encoded)

    def _writer_loop(self) -> None:
        (self._session_dir / "lidar").mkdir(parents=True, exist_ok=True)
        (self._session_dir / "camera").mkdir(parents=True, exist_ok=True)
        (self._session_dir / "camera_side").mkdir(parents=True, exist_ok=True)
        self._manifest["software_git_commit"] = self._git_commit()
        self._write_manifest()
        camera_csv = self._session_dir / "camera" / "frames.csv"
        side_camera_csv = self._session_dir / "camera_side" / "frames.csv"
        while True:
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                return
            kind, payload = item
            try:
                if kind == "camera":
                    jpeg = payload.pop("jpeg")
                    payload["writer_started_monotonic_ns"] = time.monotonic_ns()
                    payload["jpeg_sha256"] = hashlib.sha256(jpeg).hexdigest()
                    name = f"frame_{payload['sequence_number']:08d}.jpg"
                    (self._session_dir / "camera" / name).write_bytes(jpeg)
                    payload["writer_persisted_monotonic_ns"] = time.monotonic_ns()
                    new_file = not camera_csv.exists()
                    with camera_csv.open("a", encoding="utf-8", newline="") as handle:
                        writer = csv.DictWriter(handle, fieldnames=[*payload.keys(), "file"])
                        if new_file: writer.writeheader()
                        writer.writerow({**payload, "file": name})
                    self._bytes_written += len(jpeg)
                elif kind == "camera_side":
                    jpeg = payload.pop("jpeg")
                    payload["writer_started_monotonic_ns"] = time.monotonic_ns()
                    payload["jpeg_sha256"] = hashlib.sha256(jpeg).hexdigest()
                    sequence = int(payload.get("frame_counter", payload["sequence_number"]))
                    name = f"frame_{sequence:08d}.jpg"
                    (self._session_dir / "camera_side" / name).write_bytes(jpeg)
                    payload["writer_persisted_monotonic_ns"] = time.monotonic_ns()
                    new_file = not side_camera_csv.exists()
                    with side_camera_csv.open("a", encoding="utf-8", newline="") as handle:
                        writer = csv.DictWriter(handle, fieldnames=[*payload.keys(), "file"])
                        if new_file: writer.writeheader()
                        writer.writerow({**payload, "file": name})
                    self._bytes_written += len(jpeg)
                    self._side_camera_bytes += len(jpeg)
                    self._manifest["side_camera_statistics"]["frames_saved"] += 1
                elif kind == "lidar": self._append_jsonl("lidar/raw_scans.jsonl", payload)
                elif kind == "events": self._append_jsonl("events.jsonl", payload)
                elif kind == "markers": self._append_jsonl("markers.jsonl", payload)
                else: raise ValueError(f"Unsupported diagnostic record kind: {kind}")
                self._manifest["record_counts"][kind] += 1
            except Exception as exc:
                self._manifest["status"] = "PARTIAL"
                self._manifest["errors"].append(f"{type(exc).__name__}: {exc}")
            finally:
                self._queue.task_done()

    def _write_manifest(self) -> None:
        if self._session_dir:
            target = self._session_dir / "manifest.json"
            temporary = target.with_suffix(".tmp")
            temporary.write_text(json.dumps(self._manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temporary.replace(target)

    def _stop_locked(self, *, ended_at: str | None = None, reason: str = "SHUTDOWN") -> None:
        if not self.active:
            return
        self._accepting = False
        if self._finish_timer:
            self._finish_timer.cancel()
            self._finish_timer = None
        self._queue.put(None)
        if self._thread:
            self._thread.join()
        finalized_at = ended_at or datetime.now(timezone.utc).isoformat()
        self._manifest["ended_at"] = finalized_at
        self._manifest["finalized_at_utc"] = finalized_at
        self._manifest["finalized_monotonic_ns"] = time.monotonic_ns()
        self._manifest["finalize_reason"] = reason
        self._manifest["diagnostic_lifecycle"]["finish_reason"] = reason
        if self._manifest["status"] == "RECORDING":
            self._manifest["status"] = "COMPLETED"
        self._manifest["bytes_written"] = self._bytes_written
        self._finalize_side_camera_statistics()
        self._write_manifest()
        self._session_dir = None
        self._thread = None

    def _finalize_side_camera_statistics(self) -> None:
        stats = self._manifest.get("side_camera_statistics")
        if stats is None or not self._side_camera_times:
            return
        stats["first_monotonic_ns"] = self._side_camera_times[0]
        stats["last_monotonic_ns"] = self._side_camera_times[-1]
        stats["bytes_saved"] = self._side_camera_bytes
        stats["average_jpeg_bytes"] = self._side_camera_bytes / len(self._side_camera_times)
        if len(self._side_camera_times) > 1:
            intervals = [(b-a)/1e6 for a,b in zip(self._side_camera_times, self._side_camera_times[1:])]
            ordered = sorted(intervals)
            stats["median_frame_interval_ms"] = ordered[len(ordered)//2]
            stats["p95_frame_interval_ms"] = ordered[min(len(ordered)-1, int(.95*(len(ordered)-1)))]
            stats["max_frame_interval_ms"] = max(intervals)
            stats["capture_gaps_count"] = sum(x > settings.CAMERA_MAX_FRAME_GAP_MS for x in intervals)
            fps = 1000 / stats["median_frame_interval_ms"] if stats["median_frame_interval_ms"] else 0
            mb_min = stats["average_jpeg_bytes"] * fps * 60 / 1_000_000
            stats["estimated_disk_mb_per_minute"] = mb_min
            stats["estimated_disk_gb_per_hour"] = mb_min * 60 / 1000

    def stop(self, *, ended_at: str | None = None, reason: str = "SHUTDOWN") -> None:
        with self._stop_lock:
            self._stop_locked(ended_at=ended_at, reason=reason)

    def stop_in_background(self, *, ended_at: str | None = None, reason: str = "BACKGROUND_STOP") -> None:
        """Flush without making the production coordinator wait under its lock."""
        if not self.active:
            return
        threading.Thread(
            target=self.stop,
            kwargs={"ended_at": ended_at, "reason": reason},
            name="diagnostic-stopper",
            daemon=True,
        ).start()


diagnostic_recorder = CameraLidarDiagnosticRecorder()
