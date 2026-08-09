import asyncio
import logging
import time
from collections import deque
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Callable, Deque, Optional

from config import settings
from services.lidar_client import lidar_client
from services.camera_lidar_diagnostic_recorder import diagnostic_recorder


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LidarProfile:
    captured_at: str
    sequence_number: int
    points_total: int
    points_valid: int
    distances_mm: list[int]
    min_distance_mm: Optional[int]
    max_distance_mm: Optional[int]
    average_distance_mm: Optional[float]

    def to_dict(self) -> dict:
        return asdict(self)


class LidarProfileBuffer:
    """The only continuous reader of lidar scans and a bounded RAM buffer."""

    def __init__(
        self,
        client=lidar_client,
        buffer_seconds: float = settings.LIDAR_BUFFER_SECONDS,
        max_count: int = settings.LIDAR_PROFILE_MAX_COUNT,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.client = client
        self.buffer_seconds = buffer_seconds
        self.max_count = max_count
        self.clock = clock
        self._profiles: Deque[LidarProfile] = deque(maxlen=max_count)
        self._latest_raw_data: Optional[str] = None
        self._sequence = 0
        self._lock = RLock()
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.last_error: Optional[str] = None

    @property
    def reader_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def _prune(self, now: datetime) -> None:
        cutoff = now - timedelta(seconds=self.buffer_seconds)
        while self._profiles:
            captured_at = datetime.fromisoformat(self._profiles[0].captured_at)
            if captured_at >= cutoff:
                break
            self._profiles.popleft()

    def add_profile(
        self,
        distances_mm: list[int],
        *,
        points_total: Optional[int] = None,
        captured_at: Optional[datetime] = None,
        raw_data: Optional[str] = None,
    ) -> LidarProfile:
        now = captured_at or self.clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        values = list(distances_mm)
        with self._lock:
            self._sequence += 1
            profile = LidarProfile(
                captured_at=now.isoformat(),
                sequence_number=self._sequence,
                points_total=points_total if points_total is not None else len(values),
                points_valid=len(values),
                distances_mm=values,
                min_distance_mm=min(values) if values else None,
                max_distance_mm=max(values) if values else None,
                average_distance_mm=round(sum(values) / len(values), 3) if values else None,
            )
            self._profiles.append(profile)
            if raw_data is not None:
                self._latest_raw_data = raw_data
            self._prune(now)
            return deepcopy(profile)

    def profiles(self) -> list[LidarProfile]:
        with self._lock:
            self._prune(self.clock())
            return deepcopy(list(self._profiles))

    def profiles_after(self, sequence_number: int) -> list[LidarProfile]:
        return [p for p in self.profiles() if p.sequence_number > sequence_number]

    def latest_profile(self) -> Optional[LidarProfile]:
        profiles = self.profiles()
        return profiles[-1] if profiles else None

    def latest_raw_data(self) -> Optional[str]:
        with self._lock:
            return self._latest_raw_data

    def status(self) -> dict:
        profiles = self.profiles()
        return {
            "connected": bool(self.client.is_connected),
            "reader_running": self.reader_running,
            "buffer_profiles": len(profiles),
            "latest_sequence_number": profiles[-1].sequence_number if profiles else None,
            "last_profile_at": profiles[-1].captured_at if profiles else None,
            "last_error": self.last_error,
            "buffer_seconds": self.buffer_seconds,
            "max_count": self.max_count,
        }

    async def capture_once(self) -> Optional[LidarProfile]:
        if not self.client.is_connected:
            connected = await asyncio.to_thread(self.client.connect)
            if not connected:
                self.last_error = "lidar_connect_failed"
                return None

        request_started = time.monotonic_ns()
        raw_data = await asyncio.to_thread(self.client.get_scan_data)
        response_received = time.monotonic_ns()
        if not raw_data:
            self.last_error = "lidar_scan_failed"
            return None

        raw_distances = await asyncio.to_thread(self.client.parse_raw_data, raw_data)
        diagnostic_scan = None
        if diagnostic_recorder.active:
            diagnostic_scan = await asyncio.to_thread(self.client.parse_diagnostic_scan, raw_data)
        angle_filtered = self.client.filter_angle(raw_distances, 70)
        valid_distances = self.client.filter_valid_distances(angle_filtered)
        self.last_error = None
        profile = self.add_profile(
            valid_distances,
            points_total=len(raw_distances),
            raw_data=raw_data,
        )
        processing_completed = time.monotonic_ns()
        if diagnostic_scan is not None:
            diagnostic_recorder.record_lidar({
                "format_version": 2,
                "sequence_number": profile.sequence_number,
                "captured_utc": profile.captured_at,
                "captured_monotonic_ns": response_received,
                "request_started_monotonic_ns": request_started,
                "response_received_monotonic_ns": response_received,
                "processing_completed_monotonic_ns": processing_completed,
                "acquisition_latency_ms": round((response_received - request_started) / 1_000_000, 3),
                **diagnostic_scan,
                "filtered": {
                    "angle_deg": 70,
                    "min_valid_distance_mm": self.client.MIN_VALID_DISTANCE,
                    "max_valid_distance_mm": self.client.MAX_VALID_DISTANCE,
                    "ranges_mm": valid_distances,
                },
            })
        return profile

    async def _reader_loop(self) -> None:
        while self._running:
            try:
                profile = await self.capture_once()
                if profile is None:
                    await asyncio.sleep(settings.LIDAR_RECONNECT_SECONDS)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                logger.exception("Lidar reader error")
                await asyncio.sleep(settings.LIDAR_RECONNECT_SECONDS)

    async def start(self) -> None:
        if self.reader_running:
            return
        self._running = True
        self._task = asyncio.create_task(self._reader_loop(), name="lidar-profile-reader")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None


lidar_profile_buffer = LidarProfileBuffer()
