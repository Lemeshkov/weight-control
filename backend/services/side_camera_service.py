from __future__ import annotations

import logging
import os
import time
from collections import deque
from threading import Lock
from urllib.parse import unquote, urlsplit

from config import settings
from services.camera_client import CameraClient

logger = logging.getLogger(__name__)


def parse_rtsp_url(value: str) -> dict:
    parsed = urlsplit(value)
    if parsed.scheme.lower() != "rtsp" or not parsed.hostname:
        raise ValueError("CAMERA_SIDE_RTSP_URL must be a valid rtsp:// URL")
    return {
        "ip": parsed.hostname,
        "username": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "path": parsed.path or "/Streaming/Channels/101",
    }


class SideCameraService:
    """Optional health adapter around the existing latest-frame CameraClient."""

    def __init__(self, *, enabled=None, rtsp_url=None, transport=None, gap_ms=None, stale_ms=None,
                 reconnect_seconds=None, client_factory=CameraClient):
        self.enabled = settings.CAMERA_SIDE_ENABLED if enabled is None else bool(enabled)
        self._rtsp_url = settings.CAMERA_SIDE_RTSP_URL if rtsp_url is None else rtsp_url
        self.transport = (settings.CAMERA_SIDE_RTSP_TRANSPORT if transport is None else transport).lower()
        self.gap_ms = settings.CAMERA_MAX_FRAME_GAP_MS if gap_ms is None else float(gap_ms)
        self.stale_ms = settings.CAMERA_STALE_THRESHOLD_MS if stale_ms is None else float(stale_ms)
        self.reconnect_seconds = settings.CAMERA_SIDE_RECONNECT_SECONDS if reconnect_seconds is None else reconnect_seconds
        self._client_factory = client_factory
        self.client = None
        self._lock = Lock(); self._listeners = []; self._receive_times = deque(maxlen=120)
        self.frame_counter = 0; self.receive_monotonic_ns = None; self.receive_wall_ns = None
        self.frame_gap_count = 0; self.last_frame_gap_ms = None; self.last_error = None
        self.width = 0; self.height = 0

    def add_frame_listener(self, listener):
        with self._lock:
            if listener not in self._listeners:self._listeners.append(listener)

    def _on_frame(self, sample):
        receive_ns = int(sample.get("camera_frame_read_completed_monotonic_ns") or sample["captured_monotonic_ns"])
        # The parent publishes after JPEG encode, but exposes read-complete
        # monotonic time. Project the current wall clock back to that instant.
        observed_mono = time.monotonic_ns()
        wall_ns = time.time_ns() - max(0, observed_mono - receive_ns); previous = self.receive_monotonic_ns
        gap = None if previous is None else (receive_ns - previous) / 1e6
        with self._lock:
            self.frame_counter = int(sample["sequence_number"]); self.receive_monotonic_ns = receive_ns
            self.receive_wall_ns = wall_ns; self.width = int(sample.get("width") or 0); self.height = int(sample.get("height") or 0)
            self._receive_times.append(receive_ns)
            if gap is not None and gap > self.gap_ms:
                self.frame_gap_count += 1; self.last_frame_gap_ms = round(gap, 3)
            listeners = list(self._listeners)
        enriched = {**sample, "receive_monotonic_ns": receive_ns, "receive_wall_ns": wall_ns,
                    "frame_counter": self.frame_counter, "frame_gap_detected": bool(gap is not None and gap > self.gap_ms),
                    "frame_gap_ms": gap}
        for listener in listeners:
            try:listener(enriched)
            except Exception:logger.exception("SIDE_CAMERA listener failed")

    def start(self) -> bool:
        if not self.enabled:
            logger.info("SIDE_CAMERA_ENABLED=false")
            return True
        if not self._rtsp_url:
            self.last_error = "CAMERA_SIDE_RTSP_URL_MISSING"; logger.error("SIDE_CAMERA configuration missing RTSP URL")
            return False
        try:
            cfg = parse_rtsp_url(self._rtsp_url)
            if self.transport == "tcp":os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
            elif self.transport not in {"udp", "unknown"}:raise ValueError("unsupported CAMERA_SIDE_RTSP_TRANSPORT")
            self.client = self._client_factory(camera_type="ip", ip=cfg["ip"], username=cfg["username"], password=cfg["password"],
                rtsp_path=cfg["path"], capture_mode="rtsp", rtsp_fallback_to_snapshot=False,
                rtsp_reconnect_seconds=self.reconnect_seconds)
            self.client.add_frame_listener(self._on_frame); logger.info("SIDE_CAMERA_CONNECTING host=%s", cfg["ip"])
            started = bool(self.client.connect()); self.last_error = None if started else "CONNECT_FAILED"
            return started
        except Exception as exc:
            self.last_error = type(exc).__name__; logger.error("SIDE_CAMERA start failed: %s", type(exc).__name__); return False

    def stop(self):
        if self.client:self.client.disconnect()

    @property
    def measured_fps(self):
        values=list(self._receive_times)
        if len(values)<2 or values[-1]<=values[0]:return None
        return round((len(values)-1)*1e9/(values[-1]-values[0]),3)

    def status(self):
        now=time.monotonic_ns();age=None if self.receive_monotonic_ns is None else max(0,(now-self.receive_monotonic_ns)/1e6)
        connected=bool(self.client and self.client.is_connected); stale=bool(self.enabled and (age is None or age>self.stale_ms))
        return {"enabled":self.enabled,"connected":connected,"stale":stale,"measured_fps":self.measured_fps,
            "frame_age_ms":round(age,3) if age is not None else None,"frame_counter":self.frame_counter,
            "receive_monotonic_ns":self.receive_monotonic_ns,"receive_wall_ns":self.receive_wall_ns,
            "resolution":f"{self.width}x{self.height}" if self.width and self.height else None,
            "reconnect_count":int(self.client.rtsp_reconnect_count) if self.client else 0,"frame_gap_count":self.frame_gap_count,
            "last_frame_gap_ms":self.last_frame_gap_ms,"last_error":self.last_error or (None if self.client else "DISABLED" if not self.enabled else None),
            "transport_requested":self.transport}


side_camera_service = SideCameraService()
