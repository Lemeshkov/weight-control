from __future__ import annotations

import logging
import os
import queue
import re
import subprocess
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Callable, Optional

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover - production dependency
    cv2 = None

logger = logging.getLogger(__name__)


def read_exact(stream: BinaryIO, size: int, stop_event: Optional[threading.Event] = None) -> Optional[bytes]:
    """Read one complete raw frame. EOF/stop before ``size`` is never published."""
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        if stop_event is not None and stop_event.is_set():
            return None
        chunk = stream.read(remaining)
        if not chunk:
            return None
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def sanitize_ffmpeg_text(value: object, secrets: tuple[str, ...] = ()) -> str:
    text = str(value)
    text = re.sub(r"rtsp://[^\s/@:]+(?::[^\s/@]*)?@", "rtsp://<redacted>@", text, flags=re.IGNORECASE)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "<redacted>")
    return text[:1000]


def build_ffmpeg_command(executable: str, rtsp_url: str, width: int, height: int) -> list[str]:
    return [
        executable,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-rtsp_transport",
        "tcp",
        "-i",
        rtsp_url,
        "-an",
        "-sn",
        "-dn",
        "-vf",
        f"scale={width}:{height}",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "pipe:1",
    ]


class SideCameraFfmpegReader:
    """Single supervised external-FFmpeg reader for the permanent side camera."""

    reader_backend = "external_ffmpeg"
    active_capture_mode = "rtsp"

    def __init__(
        self,
        *,
        rtsp_url: str,
        ffmpeg_path: str,
        width: int,
        height: int,
        reconnect_seconds: float = 1.0,
        shutdown_timeout: float = 3.0,
        stale_ms: float = 1000.0,
        popen_factory: Callable[..., Any] = subprocess.Popen,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
    ):
        self.rtsp_url = rtsp_url
        self.ffmpeg_path = str(ffmpeg_path)
        configured_path = Path(self.ffmpeg_path).expanduser()
        self._resolved_ffmpeg_path = configured_path if configured_path.is_absolute() else Path(__file__).resolve().parents[2] / configured_path
        self.width = int(width)
        self.height = int(height)
        if self.width <= 0 or self.height <= 0:
            raise ValueError("SIDE_CAMERA_FRAME_DIMENSIONS_INVALID")
        self.frame_bytes = self.width * self.height * 3
        self.reconnect_seconds = max(0.05, float(reconnect_seconds))
        self.shutdown_timeout = max(0.1, float(shutdown_timeout))
        self.stale_ms = float(stale_ms)
        self._popen_factory = popen_factory
        self._clock = monotonic_ns
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._supervisor_thread: Optional[threading.Thread] = None
        self._dispatch_thread: Optional[threading.Thread] = None
        self._process = None
        self._listeners: list[Callable[[dict], None]] = []
        self._dispatch_queue: queue.Queue = queue.Queue(maxsize=1)
        self._current_jpeg: Optional[bytes] = None
        self._frame_sequence = 0
        self._last_frame_monotonic_ns: Optional[int] = None
        self._frame_timestamp: Optional[datetime] = None
        self._published_monotonic_ns = deque(maxlen=120)
        self._stderr_lines = deque(maxlen=20)
        self.rtsp_reconnect_count = 0
        self.dropped_dispatch_frames = 0
        self.bad_frames = 0
        self.last_error: Optional[str] = None
        self._ever_spawned = False
        self._current_process_has_frame = False

    def add_frame_listener(self, listener) -> None:
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def remove_frame_listener(self, listener) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    @property
    def ffmpeg_process_alive(self) -> bool:
        process = self._process
        return bool(process is not None and process.poll() is None)

    @property
    def last_frame_monotonic_ns(self) -> Optional[int]:
        return self._last_frame_monotonic_ns

    @property
    def is_connected(self) -> bool:
        last = self._last_frame_monotonic_ns
        if last is None or not self.ffmpeg_process_alive or not self._current_process_has_frame:
            return False
        return (self._clock() - last) / 1_000_000 <= self.stale_ms

    @property
    def acquisition_fps(self) -> Optional[float]:
        values = list(self._published_monotonic_ns)
        if len(values) < 2 or values[-1] <= values[0]:
            return None
        return round((len(values) - 1) * 1_000_000_000 / (values[-1] - values[0]), 3)

    @property
    def stderr_diagnostics(self) -> list[str]:
        return list(self._stderr_lines)

    def connect(self) -> bool:
        if cv2 is None:
            self.last_error = "OPENCV_JPEG_ENCODER_UNAVAILABLE"
            logger.error("SIDE_CAMERA unavailable: %s", self.last_error)
            return False
        executable = self._resolved_ffmpeg_path
        if not executable.is_file():
            self.last_error = "FFMPEG_EXECUTABLE_NOT_FOUND"
            logger.error("SIDE_CAMERA unavailable: %s path=%s", self.last_error, executable)
            return False
        if self._supervisor_thread and self._supervisor_thread.is_alive():
            return True
        self._stop_event.clear()
        self._dispatch_thread = threading.Thread(target=self._dispatch_loop, name="side-camera-dispatch", daemon=True)
        self._supervisor_thread = threading.Thread(target=self._supervise, name="side-camera-ffmpeg", daemon=True)
        self._dispatch_thread.start()
        self._supervisor_thread.start()
        return True

    def _spawn(self):
        command = build_ffmpeg_command(str(self._resolved_ffmpeg_path), self.rtsp_url, self.width, self.height)
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        return self._popen_factory(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            bufsize=0,
            creationflags=creationflags,
        )

    def _supervise(self) -> None:
        while not self._stop_event.is_set():
            process = None
            stderr_thread = None
            try:
                if self._ever_spawned:
                    self.rtsp_reconnect_count += 1
                self._ever_spawned = True
                process = self._spawn()
                self._process = process
                self._current_process_has_frame = False
                stderr_thread = threading.Thread(
                    target=self._drain_stderr, args=(process.stderr,), name="side-camera-ffmpeg-stderr", daemon=True
                )
                stderr_thread.start()
                self.last_error = None
                while not self._stop_event.is_set():
                    raw = read_exact(process.stdout, self.frame_bytes, self._stop_event)
                    if raw is None:
                        if self._stop_event.is_set():
                            break
                        self.bad_frames += 1
                        self.last_error = "FFMPEG_STDOUT_EOF_OR_PARTIAL_FRAME"
                        break
                    # Authoritative synchronization timestamp: host monotonic clock,
                    # assigned only after the complete decoded raw frame arrived.
                    captured_ns = self._clock()
                    if self._last_frame_monotonic_ns is not None:
                        captured_ns = max(captured_ns, self._last_frame_monotonic_ns + 1)
                    self._publish_raw(raw, captured_ns)
            except Exception as exc:
                self.last_error = sanitize_ffmpeg_text(type(exc).__name__)
                logger.warning("SIDE_CAMERA FFmpeg reader failed: %s", self.last_error)
            finally:
                if process is not None:
                    self._terminate_process(process)
                self._process = None
                self._current_process_has_frame = False
                if stderr_thread is not None:
                    stderr_thread.join(timeout=self.shutdown_timeout)
            if not self._stop_event.wait(self.reconnect_seconds):
                logger.warning("SIDE_CAMERA FFmpeg reconnect scheduled")

    def _publish_raw(self, raw: bytes, captured_ns: int) -> bool:
        frame = np.frombuffer(raw, dtype=np.uint8).reshape((self.height, self.width, 3))
        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        if not ok:
            self.bad_frames += 1
            self.last_error = "JPEG_ENCODE_FAILED"
            return False
        jpeg = encoded.tobytes()
        captured_at = datetime.now(timezone.utc)
        with self._lock:
            self._last_frame_monotonic_ns = captured_ns
            self._current_process_has_frame = True
            self._published_monotonic_ns.append(captured_ns)
            self._frame_sequence += 1
            sequence = self._frame_sequence
            self._current_jpeg = jpeg
            self._frame_timestamp = captured_at
        published_ns = self._clock()
        sample = {
            "sequence_number": sequence,
            "captured_utc": captured_at.isoformat(),
            "captured_monotonic_ns": captured_ns,
            "camera_frame_read_completed_monotonic_ns": captured_ns,
            "camera_decode_completed_monotonic_ns": captured_ns,
            "frame_published_monotonic_ns": published_ns,
            "processing_completed_monotonic_ns": published_ns,
            "jpeg": jpeg,
            "width": self.width,
            "height": self.height,
        }
        try:
            self._dispatch_queue.put_nowait(sample)
        except queue.Full:
            try:
                self._dispatch_queue.get_nowait()
                self._dispatch_queue.task_done()
            except queue.Empty:
                pass
            self.dropped_dispatch_frames += 1
            self._dispatch_queue.put_nowait(sample)
        return True

    def _dispatch_loop(self) -> None:
        while not self._stop_event.is_set() or not self._dispatch_queue.empty():
            try:
                sample = self._dispatch_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                with self._lock:
                    listeners = list(self._listeners)
                for listener in listeners:
                    try:
                        listener(sample)
                    except Exception:
                        logger.exception("SIDE_CAMERA frame listener failed")
            finally:
                self._dispatch_queue.task_done()

    def _drain_stderr(self, stream) -> None:
        if stream is None:
            return
        secrets = (self.rtsp_url,)
        try:
            while not self._stop_event.is_set():
                line = stream.readline()
                if not line:
                    return
                safe = sanitize_ffmpeg_text(line.decode("utf-8", errors="replace").strip(), secrets)
                if safe:
                    self._stderr_lines.append(safe)
        except Exception as exc:
            self._stderr_lines.append(sanitize_ffmpeg_text(type(exc).__name__))

    def _terminate_process(self, process) -> None:
        try:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=self.shutdown_timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=self.shutdown_timeout)
            except subprocess.TimeoutExpired:
                logger.error("SIDE_CAMERA FFmpeg process could not be reaped after kill")
        except Exception as exc:
            logger.warning("SIDE_CAMERA FFmpeg cleanup failed: %s", type(exc).__name__)
        finally:
            for stream_name in ("stdout", "stderr"):
                stream = getattr(process, stream_name, None)
                try:
                    if stream is not None:
                        stream.close()
                except Exception:
                    pass

    def get_frame(self) -> Optional[dict]:
        if not self.is_connected:
            return None
        with self._lock:
            if self._current_jpeg is None:
                return None
            return {
                "timestamp": self._frame_timestamp.isoformat() if self._frame_timestamp else None,
                "data": self._current_jpeg,
                "size": len(self._current_jpeg),
                "width": self.width,
                "height": self.height,
                "sequence_number": self._frame_sequence,
            }

    def disconnect(self) -> None:
        self._stop_event.set()
        process = self._process
        if process is not None:
            self._terminate_process(process)
        if self._supervisor_thread:
            self._supervisor_thread.join(timeout=self.shutdown_timeout)
        if self._dispatch_thread:
            self._dispatch_thread.join(timeout=self.shutdown_timeout)
        self._process = None
        with self._lock:
            self._current_jpeg = None
