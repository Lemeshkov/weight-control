import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from config import settings
from services.lidar_pass_storage import AtomicLidarPassStorage, lidar_pass_storage
from services.lidar_profile_buffer import LidarProfile, LidarProfileBuffer, lidar_profile_buffer
from services.lidar_session_repository import (
    LidarSessionRepository,
    SqlAlchemyLidarSessionRepository,
)


logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ActiveLidarPass:
    session_key: str
    status: str
    workflow_state: str
    started_at: datetime
    load_scale_at: datetime
    trigger_weight_kg: float
    trip_id: Optional[int] = None
    repository_id: Optional[int] = None
    stable_weight_at: Optional[datetime] = None
    stable_weight_kg: Optional[float] = None
    maximum_observed_weight_kg: float = 0
    weight_samples_count: int = 0
    ended_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    pre_trigger_profiles_count: int = 0
    profiles: list[LidarProfile] = field(default_factory=list)
    last_sequence_number: int = 0
    data_file_path: Optional[str] = None
    error_message: Optional[str] = None
    state_timestamps: dict[str, str] = field(default_factory=dict)

    @property
    def recording(self) -> bool:
        return self.status == "RECORDING"


class WeighingLidarCoordinator:
    def __init__(
        self,
        buffer: LidarProfileBuffer = lidar_profile_buffer,
        repository: Optional[LidarSessionRepository] = None,
        storage: AtomicLidarPassStorage = lidar_pass_storage,
        stable_confirm_samples: int = settings.SCALE_STABLE_CONFIRM_SAMPLES,
        post_stable_seconds: float = settings.LIDAR_POST_STABLE_SECONDS,
        empty_threshold_kg: float = settings.SCALE_EMPTY_THRESHOLD_KG,
        empty_confirm_samples: int = settings.SCALE_EMPTY_CONFIRM_SAMPLES,
    ):
        self.buffer = buffer
        self.repository = repository or SqlAlchemyLidarSessionRepository()
        self.storage = storage
        self.stable_confirm_samples = stable_confirm_samples
        self.post_stable_seconds = post_stable_seconds
        self.empty_threshold_kg = empty_threshold_kg
        self.empty_confirm_samples = empty_confirm_samples
        self.active_session: Optional[ActiveLidarPass] = None
        self.last_scale_snapshot: Optional[dict] = None
        self.scale_connected = False
        self.persistence_available = True
        self.persistence_error: Optional[str] = None
        self._previous_state_name: Optional[str] = None
        self._stable_samples = 0
        self._empty_samples = 0
        self._seen_unload = False
        self._lock = asyncio.Lock()
        self._finish_task: Optional[asyncio.Task] = None

    async def check_persistence(self) -> bool:
        try:
            self.persistence_available = await asyncio.to_thread(self.repository.is_available)
            self.persistence_error = None if self.persistence_available else "lidar_pass_sessions table is missing"
        except Exception as exc:
            self.persistence_available = False
            self.persistence_error = f"{type(exc).__name__}: {exc}"
        return self.persistence_available

    @staticmethod
    def _normalise_snapshot(data: dict) -> dict:
        raw = data.get("full_response") if isinstance(data.get("full_response"), dict) else data
        return {
            "state_name": str(raw.get("StateName") or data.get("state") or ""),
            "state": raw.get("State"),
            "massa": float(raw.get("Massa", data.get("weight", 0)) or 0),
            "stabil": bool(raw.get("Stabil", data.get("is_stable", False))),
            "enable": raw.get("Enable"),
            "rx_packet": raw.get("RxPacket"),
            "unit_meas": raw.get("UnitMeas"),
            "captured_at": utc_now().isoformat(),
        }

    def _repository_values(self, session: ActiveLidarPass) -> dict:
        profiles = session.profiles
        valid_profiles = sum(1 for profile in profiles if profile.points_valid > 0)
        return {
            "trip_id": session.trip_id,
            "status": session.status,
            "workflow_state": session.workflow_state,
            "trigger_type": "LOAD_SCALE",
            "trigger_state_name": "LoadScale",
            "started_at": session.started_at,
            "load_scale_at": session.load_scale_at,
            "stable_weight_at": session.stable_weight_at,
            "ended_at": session.ended_at,
            "completed_at": session.completed_at,
            "pre_trigger_seconds": self.buffer.buffer_seconds,
            "pre_trigger_profiles_count": session.pre_trigger_profiles_count,
            "profiles_count": len(profiles),
            "valid_profiles_count": valid_profiles,
            "points_total": sum(profile.points_total for profile in profiles),
            "points_valid": sum(profile.points_valid for profile in profiles),
            "trigger_weight_kg": session.trigger_weight_kg,
            "stable_weight_kg": session.stable_weight_kg,
            "maximum_observed_weight_kg": session.maximum_observed_weight_kg,
            "weight_samples_count": session.weight_samples_count,
            "state_timestamps": session.state_timestamps,
            "estimated_volume_m3": None,
            "volume_status": "NOT_CALCULATED",
            "data_file_path": session.data_file_path,
            "error_message": session.error_message,
        }

    async def _create_repository_record(self, session: ActiveLidarPass) -> None:
        try:
            session.repository_id = await asyncio.to_thread(
                self.repository.create, self._repository_values(session)
            )
            self.persistence_available = True
            self.persistence_error = None
        except Exception as exc:
            self.persistence_available = False
            self.persistence_error = f"{type(exc).__name__}: {exc}"
            logger.error("Lidar session persistence unavailable: %s", self.persistence_error)

    async def _update_repository(self, session: ActiveLidarPass) -> None:
        if session.repository_id is None:
            return
        try:
            await asyncio.to_thread(
                self.repository.update,
                session.repository_id,
                self._repository_values(session),
            )
            self.persistence_available = True
            self.persistence_error = None
        except Exception as exc:
            self.persistence_available = False
            self.persistence_error = f"{type(exc).__name__}: {exc}"
            logger.error("Failed to update lidar session metadata: %s", self.persistence_error)

    def _sync_profiles(self, session: ActiveLidarPass) -> None:
        if not session.recording:
            return
        new_profiles = self.buffer.profiles_after(session.last_sequence_number)
        if new_profiles:
            session.profiles.extend(new_profiles)
            session.last_sequence_number = new_profiles[-1].sequence_number

    async def _open_session(self, snapshot: dict, now: datetime) -> None:
        if self.active_session is not None:
            return
        profiles = self.buffer.profiles()
        last_sequence = profiles[-1].sequence_number if profiles else 0
        session = ActiveLidarPass(
            session_key=uuid.uuid4().hex,
            status="RECORDING",
            workflow_state="ENTERING_AND_SCANNING",
            started_at=datetime.fromisoformat(profiles[0].captured_at) if profiles else now,
            load_scale_at=now,
            trigger_weight_kg=snapshot["massa"],
            maximum_observed_weight_kg=snapshot["massa"],
            weight_samples_count=1,
            pre_trigger_profiles_count=len(profiles),
            profiles=profiles,
            last_sequence_number=last_sequence,
            state_timestamps={"ENTERING_AND_SCANNING": now.isoformat()},
        )
        self.active_session = session
        await self._create_repository_record(session)

    async def _finish_after_delay(self, session_key: str) -> None:
        await asyncio.sleep(self.post_stable_seconds)
        async with self._lock:
            session = self.active_session
            if session is None or session.session_key != session_key or not session.recording:
                return
            self._sync_profiles(session)
            await self._finalise_recording(session)

    async def _finalise_recording(self, session: ActiveLidarPass) -> None:
        session.ended_at = utc_now()
        if not session.profiles:
            session.status = "FAILED"
            session.error_message = self.buffer.last_error or "lidar_profiles_unavailable"
            await self._update_repository(session)
            return

        metadata = self._repository_values(session)
        metadata.update({
            "session_key": session.session_key,
            "started_at": session.started_at.isoformat(),
            "load_scale_at": session.load_scale_at.isoformat(),
            "stable_weight_at": session.stable_weight_at.isoformat() if session.stable_weight_at else None,
            "ended_at": session.ended_at.isoformat(),
        })
        try:
            session.data_file_path = await asyncio.to_thread(
                self.storage.save,
                metadata,
                [profile.to_dict() for profile in session.profiles],
            )
            session.status = "COMPLETED"
        except Exception as exc:
            session.status = "FAILED"
            session.error_message = f"json_write_failed:{type(exc).__name__}: {exc}"
        await self._update_repository(session)

    async def on_scale_unavailable(self) -> None:
        async with self._lock:
            self.scale_connected = False

    async def on_scale_snapshot(self, data: dict) -> None:
        snapshot = self._normalise_snapshot(data)
        now = utc_now()
        async with self._lock:
            self.scale_connected = True
            self.last_scale_snapshot = snapshot
            state_name = snapshot["state_name"]
            state_changed = state_name != self._previous_state_name

            if state_changed and state_name == "LoadScale":
                await self._open_session(snapshot, now)

            session = self.active_session
            if session is not None:
                self._sync_profiles(session)
                session.maximum_observed_weight_kg = max(
                    session.maximum_observed_weight_kg, snapshot["massa"]
                )
                session.weight_samples_count += 1

                state_map = {
                    "Weighing": "WEIGHING",
                    "ReadyWeighing": "READY",
                    "WeighingComplete": "WAITING_DEPARTURE",
                    "UnLoadScale": "LEAVING",
                }
                workflow_state = state_map.get(state_name)
                if workflow_state and workflow_state != session.workflow_state:
                    session.workflow_state = workflow_state
                    session.state_timestamps[workflow_state] = now.isoformat()

                if state_name == "Weighing" and snapshot["stabil"] and session.stable_weight_at is None:
                    self._stable_samples += 1
                    if self._stable_samples >= self.stable_confirm_samples:
                        session.stable_weight_at = now
                        session.stable_weight_kg = snapshot["massa"]
                        session.workflow_state = "WEIGHT_CAPTURED"
                        session.state_timestamps["WEIGHT_CAPTURED"] = now.isoformat()
                        self._finish_task = asyncio.create_task(
                            self._finish_after_delay(session.session_key),
                            name="lidar-post-stable-finish",
                        )
                elif session.stable_weight_at is None:
                    self._stable_samples = 0

                if state_name == "UnLoadScale":
                    self._seen_unload = True
                if (
                    self._seen_unload
                    and state_name == "Empty"
                    and snapshot["stabil"]
                    and snapshot["massa"] <= self.empty_threshold_kg
                ):
                    self._empty_samples += 1
                    if self._empty_samples >= self.empty_confirm_samples:
                        session.completed_at = now
                        session.workflow_state = "COMPLETED"
                        session.state_timestamps["COMPLETED"] = now.isoformat()
                        await self._update_repository(session)
                        self.active_session = None
                        self._stable_samples = 0
                        self._empty_samples = 0
                        self._seen_unload = False
                else:
                    self._empty_samples = 0

            self._previous_state_name = state_name

    async def bind_trip(self, trip_id: int) -> bool:
        async with self._lock:
            session = self.active_session
            if session is None:
                return False
            if session.trip_id == trip_id:
                return True
            if session.trip_id is not None:
                return False
            session.trip_id = trip_id
            await self._update_repository(session)
            return True

    def current_state(self) -> dict:
        session = self.active_session
        snapshot = self.last_scale_snapshot or {}
        return {
            "scale": {
                "state_name": snapshot.get("state_name"),
                "massa": snapshot.get("massa"),
                "stabil": snapshot.get("stabil"),
                "connected": self.scale_connected,
            },
            "lidar": {
                **self.buffer.status(),
                "recording": bool(session and session.recording),
                "session_profiles": len(session.profiles) if session else 0,
            },
            "active_session": self.session_state(),
            "persistence_available": self.persistence_available,
            "persistence_error": self.persistence_error,
        }

    def session_state(self) -> Optional[dict]:
        session = self.active_session
        if session is None:
            return None
        return {
            "id": session.repository_id,
            "session_key": session.session_key,
            "status": session.status,
            "workflow_state": session.workflow_state,
            "trip_id": session.trip_id,
            "started_at": session.started_at.isoformat(),
            "load_scale_at": session.load_scale_at.isoformat(),
            "stable_weight_at": session.stable_weight_at.isoformat() if session.stable_weight_at else None,
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
            "profiles_count": len(session.profiles),
            "pre_trigger_profiles_count": session.pre_trigger_profiles_count,
            "data_file_path": session.data_file_path,
            "error_message": session.error_message,
            "volume_status": "NOT_CALCULATED",
            "estimated_volume_m3": None,
        }

    async def stop(self) -> None:
        if self._finish_task and not self._finish_task.done():
            self._finish_task.cancel()
            try:
                await self._finish_task
            except asyncio.CancelledError:
                pass


weighing_lidar_coordinator = WeighingLidarCoordinator()
