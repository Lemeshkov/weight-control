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


class CameraLidarDiagnosticRecorder:
    """Non-blocking, opt-in writer for one physical pass."""

    def __init__(self, *, enabled=None, base_dir=None, queue_size=None, max_duration_sec=None, max_bytes=None,
                 camera_max_fps=None):
        self.enabled = settings.CAMERA_LIDAR_DIAGNOSTIC_RECORDING if enabled is None else enabled
        self.base_dir = Path(base_dir or settings.DIAGNOSTIC_DATA_DIR)
        self.queue_size = queue_size or settings.DIAGNOSTIC_QUEUE_SIZE
        self.max_duration_sec = max_duration_sec or settings.DIAGNOSTIC_MAX_DURATION_SEC
        self.max_bytes = max_bytes or settings.DIAGNOSTIC_MAX_BYTES
        self.camera_max_fps = settings.DIAGNOSTIC_CAMERA_MAX_FPS if camera_max_fps is None else camera_max_fps
        self._queue: queue.Queue = queue.Queue(maxsize=self.queue_size)
        self._thread: threading.Thread | None = None
        self._session_dir: Path | None = None
        self._manifest: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._bytes_written = 0
        self._camera_sequences_seen: set[int] = set()
        self._last_camera_recorded_monotonic_ns: Optional[int] = None

    @property
    def active(self) -> bool:
        return self._session_dir is not None

    def attach_camera(self, camera_client) -> None:
        camera_client.add_frame_listener(self.record_camera)

    @staticmethod
    def _git_commit() -> str | None:
        try:
            return subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=1, check=True
            ).stdout.strip()
        except Exception:
            return None

    def start(self, session_key: str, *, started_at: str, trip_id=None, camera_config=None) -> None:
        if not self.enabled or self.active:
            return
        session_dir = self.base_dir / session_key
        self._session_dir = session_dir
        self._bytes_written = 0
        self._camera_sequences_seen = set()
        self._last_camera_recorded_monotonic_ns = None
        self._manifest = {
            "format_version": 2, "status": "RECORDING", "session_key": session_key,
            "trip_id": trip_id, "started_at": started_at, "started_monotonic_ns": time.monotonic_ns(),
            "software_git_commit": None, "camera_configuration": camera_config or {},
            "lidar_configuration": {"source": "per-profile LMDscandata.DIST1"},
            "record_counts": {"lidar": 0, "camera": 0, "events": 0, "markers": 0},
            "camera_duplicate_sequence_count": 0,
            "camera_sampled_out_count": 0,
            "dropped_record_count": 0, "errors": [],
            "limits": {
                "max_duration_sec": self.max_duration_sec,
                "max_bytes": self.max_bytes,
                "queue_size": self.queue_size,
                "camera_max_fps": self.camera_max_fps,
            },
        }
        self._thread = threading.Thread(target=self._writer_loop, name="diagnostic-writer", daemon=True)
        self._thread.start()

    def _enqueue(self, kind: str, payload: dict) -> None:
        if not self.active:
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
        if not self.active:
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

    def record_lidar(self, sample: dict) -> None:
        if self.active and self._manifest["lidar_configuration"].get("beam_count") is None:
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

    def bind_trip(self, trip_id: int) -> None:
        if self.active:
            self._manifest["trip_id"] = trip_id
            self.record_event("TRIP_BOUND", trip_id=trip_id)

    def marker(self, label: str) -> bool:
        if label not in {"MOVING", "STOPPED", "RESUMED"} or not self.active:
            return False
        self._enqueue("markers", {
            "type": "marker",
            "event": "OPERATOR_MARKER",
            "captured_utc": datetime.now(timezone.utc).isoformat(),
            "captured_monotonic_ns": time.monotonic_ns(),
            "payload": {"label": label},
        })
        return True

    def _append_jsonl(self, relative: str, payload: dict) -> None:
        encoded = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        with (self._session_dir / relative).open("ab") as handle:
            handle.write(encoded)
        self._bytes_written += len(encoded)

    def _writer_loop(self) -> None:
        (self._session_dir / "lidar").mkdir(parents=True, exist_ok=True)
        (self._session_dir / "camera").mkdir(parents=True, exist_ok=True)
        self._manifest["software_git_commit"] = self._git_commit()
        self._write_manifest()
        camera_csv = self._session_dir / "camera" / "frames.csv"
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

    def stop(self, *, ended_at: str | None = None) -> None:
        if not self.active:
            return
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout=10)
        self._manifest["ended_at"] = ended_at or datetime.now(timezone.utc).isoformat()
        if self._manifest["status"] == "RECORDING": self._manifest["status"] = "COMPLETED"
        self._manifest["bytes_written"] = self._bytes_written
        self._write_manifest()
        self._session_dir = None
        self._thread = None

    def stop_in_background(self, *, ended_at: str | None = None) -> None:
        """Flush without making the production coordinator wait under its lock."""
        if not self.active:
            return
        threading.Thread(
            target=self.stop,
            kwargs={"ended_at": ended_at},
            name="diagnostic-stopper",
            daemon=True,
        ).start()


diagnostic_recorder = CameraLidarDiagnosticRecorder()
