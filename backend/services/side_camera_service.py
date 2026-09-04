from __future__ import annotations

import logging
import time
from collections import deque
from threading import Lock
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from config import settings
from services.side_camera_ffmpeg_reader import SideCameraFfmpegReader

logger = logging.getLogger(__name__)


def parse_rtsp_url(value: str) -> dict:
    parsed = urlsplit(value)
    if parsed.scheme.lower() != "rtsp" or not parsed.hostname:
        raise ValueError("CAMERA_SIDE_RTSP_URL must be a valid rtsp:// URL")
    return {
        "ip": parsed.hostname,
        "port": parsed.port or 554,
        "username": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "path": parsed.path or "",
    }


def build_credentialed_rtsp_url(value: str, username: str = "", password: str = "") -> str:
    parsed = urlsplit(value)
    if parsed.scheme.lower() != "rtsp" or not parsed.hostname:
        raise ValueError("CAMERA_SIDE_RTSP_URL must be a valid rtsp:// URL")
    existing_user = unquote(parsed.username or "")
    existing_password = unquote(parsed.password or "")
    user = existing_user or username
    secret = existing_password or password
    credentials = f"{quote(user, safe='')}:{quote(secret, safe='')}@" if user else ""
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    netloc = f"{credentials}{host}:{parsed.port or 554}"
    return urlunsplit(("rtsp", netloc, parsed.path or "", parsed.query, parsed.fragment))


class SideCameraService:
    """Optional health adapter around the existing latest-frame CameraClient."""

    def __init__(self, *, enabled=None, rtsp_url=None, host=None, port=None, username=None, password=None,
                 rtsp_path=None, transport=None, gap_ms=None, stale_ms=None,
                 reconnect_seconds=None, ffmpeg_path=None, frame_width=None, frame_height=None,
                 client_factory=SideCameraFfmpegReader):
        self.enabled = settings.CAMERA_SIDE_ENABLED if enabled is None else bool(enabled)
        self._rtsp_url = settings.CAMERA_SIDE_RTSP_URL if rtsp_url is None else rtsp_url
        self.host = settings.CAMERA_SIDE_HOST if host is None else host
        self.port = settings.CAMERA_SIDE_PORT if port is None else int(port)
        self.username = settings.CAMERA_SIDE_USERNAME if username is None else username
        self._password = settings.CAMERA_SIDE_PASSWORD if password is None else password
        self.rtsp_path = settings.CAMERA_SIDE_RTSP_PATH if rtsp_path is None else rtsp_path
        self.transport = (settings.CAMERA_SIDE_RTSP_TRANSPORT if transport is None else transport).lower()
        self.gap_ms = settings.CAMERA_MAX_FRAME_GAP_MS if gap_ms is None else float(gap_ms)
        self.stale_ms = settings.CAMERA_STALE_THRESHOLD_MS if stale_ms is None else float(stale_ms)
        self.reconnect_seconds = settings.CAMERA_SIDE_RECONNECT_SECONDS if reconnect_seconds is None else reconnect_seconds
        self.ffmpeg_path = settings.SIDE_CAMERA_FFMPEG_PATH if ffmpeg_path is None else ffmpeg_path
        self.frame_width = settings.SIDE_CAMERA_FRAME_WIDTH if frame_width is None else int(frame_width)
        self.frame_height = settings.SIDE_CAMERA_FRAME_HEIGHT if frame_height is None else int(frame_height)
        self._client_factory = client_factory
        self.client = None
        self._lock = Lock(); self._listeners = []; self._receive_times = deque(maxlen=120)
        self.frame_counter = 0; self.receive_monotonic_ns = None; self.receive_wall_ns = None
        self.frame_gap_count = 0; self.last_frame_gap_ms = None; self.last_error = None
        self.width = 0; self.height = 0

    @property
    def configured(self):
        return bool(self._rtsp_url or self.rtsp_path)

    @property
    def redacted_endpoint(self):
        return f"rtsp://{self.host}:{self.port}/..." if self.configured else None

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
        if not self._rtsp_url and not self.rtsp_path:
            self.last_error = "CAMERA_SIDE_STREAM_URL_REQUIRED"; logger.error("SIDE_CAMERA configuration missing verified RTSP path")
            return False
        try:
            cfg = parse_rtsp_url(self._rtsp_url) if self._rtsp_url else {
                "ip": self.host, "port": self.port, "username": self.username, "password": self._password, "path": self.rtsp_path,
            }
            if self._rtsp_url:
                cfg["username"] = cfg["username"] or self.username
                cfg["password"] = cfg["password"] or self._password
            self.host = cfg["ip"]
            if self.transport != "tcp":raise ValueError("SIDE_CAMERA_EXTERNAL_FFMPEG_REQUIRES_TCP")
            base_url = self._rtsp_url or f"rtsp://{cfg['ip']}:{cfg['port']}{cfg['path']}"
            stream_url = build_credentialed_rtsp_url(base_url, cfg["username"], cfg["password"])
            self.client = self._client_factory(rtsp_url=stream_url, ffmpeg_path=self.ffmpeg_path,
                width=self.frame_width, height=self.frame_height, reconnect_seconds=self.reconnect_seconds,
                shutdown_timeout=settings.SIDE_CAMERA_SHUTDOWN_TIMEOUT_SECONDS, stale_ms=self.stale_ms)
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
        client_error=getattr(self.client,"last_error",None) if self.client else None
        return {"enabled":self.enabled,"configured":self.configured,"connected":connected,"receiving_frames":bool(connected and age is not None and age<=self.stale_ms),"stale":stale,"measured_fps":self.measured_fps,"actual_fps":self.measured_fps,"target_fps":settings.SIDE_CAMERA_TARGET_FPS,
            "frame_age_ms":round(age,3) if age is not None else None,"frame_counter":self.frame_counter,
            "receive_monotonic_ns":self.receive_monotonic_ns,"receive_wall_ns":self.receive_wall_ns,
            "resolution":f"{self.width}x{self.height}" if self.width and self.height else None,
            "reconnect_count":int(self.client.rtsp_reconnect_count) if self.client else 0,"frame_gap_count":self.frame_gap_count,
            "last_frame_gap_ms":self.last_frame_gap_ms,"last_error":client_error or self.last_error or (None if self.client else "DISABLED" if not self.enabled else None),
            "last_error_sanitized":client_error or self.last_error,"reader_backend":"external_ffmpeg",
            "ffmpeg_process_alive":bool(self.client and getattr(self.client,"ffmpeg_process_alive",False)),
            "last_frame_monotonic_ns":getattr(self.client,"last_frame_monotonic_ns",None) if self.client else None,
            "transport_requested":self.transport,"configured_host":self.host,"redacted_endpoint":self.redacted_endpoint,"stream_type":"RTSP" if self.configured else "UNIDENTIFIED"}


side_camera_service = SideCameraService()
