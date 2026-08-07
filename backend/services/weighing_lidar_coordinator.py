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
    InMemoryLidarSessionRepository,
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
        memory_repository: Optional[InMemoryLidarSessionRepository] = None,
        storage: AtomicLidarPassStorage = lidar_pass_storage,
        stable_confirm_samples: int = settings.SCALE_STABLE_CONFIRM_SAMPLES,
        post_stable_seconds: float = settings.LIDAR_POST_STABLE_SECONDS,
        empty_threshold_kg: float = settings.SCALE_EMPTY_THRESHOLD_KG,
        empty_confirm_samples: int = settings.SCALE_EMPTY_CONFIRM_SAMPLES,
    ):
        self.buffer = buffer
        self.repository = repository or SqlAlchemyLidarSessionRepository()
        self.memory_repository = memory_repository or InMemoryLidarSessionRepository()
        self.repository_mode = (
            "sql" if isinstance(self.repository, SqlAlchemyLidarSessionRepository) else "memory"
        )
        self.storage = storage
        self.stable_confirm_samples = stable_confirm_samples
        self.post_stable_seconds = post_stable_seconds
        self.empty_threshold_kg = empty_threshold_kg
        self.empty_confirm_samples = empty_confirm_samples
        self.active_session: Optional[ActiveLidarPass] = None
        self.last_session: Optional[ActiveLidarPass] = None
        self.last_scale_snapshot: Optional[dict] = None
        self.scale_connected = False
        self.persistence_available = self.repository_mode == "sql"
        self.persistence_error: Optional[str] = (
            None if self.persistence_available else "SQL persistence is not configured"
        )
        self._previous_state_name: Optional[str] = None
        self._stable_samples = 0
        self._last_stable_reset_reason: Optional[str] = None
        self._last_stable_sample_at: Optional[datetime] = None
        self._last_logged_fsm: Optional[tuple] = None
        self._empty_samples = 0
        self._seen_unload = False
        self._lock = asyncio.Lock()
        self._finish_task: Optional[asyncio.Task] = None
        self._current_lifecycle_token: Optional[str] = None

    async def check_persistence(self) -> bool:
        if self.repository_mode == "memory":
            return False
        try:
            available = await asyncio.to_thread(self.repository.is_available)
            if not available:
                self._switch_to_memory("lidar_pass_sessions table is missing")
            else:
                self.persistence_available = True
                self.persistence_error = None
        except Exception as exc:
            self._switch_to_memory(self._persistence_error(exc))
        return self.persistence_available

    @staticmethod
    def _persistence_error(exc: Exception) -> str:
        message = str(exc).lower()
        if "lidar_pass_sessions" in message and (
            "does not exist" in message or "undefinedtable" in message
        ):
            return "lidar_pass_sessions table is missing"
        return f"{type(exc).__name__}: {exc}"

    def _switch_to_memory(self, error: str) -> None:
        if self.repository_mode != "memory":
            logger.warning("Switching lidar session repository to memory: %s", error)
        self.repository = self.memory_repository
        self.repository_mode = "memory"
        self.persistence_available = False
        self.persistence_error = error

    @staticmethod
    def _normalise_snapshot(data: dict) -> dict:
        raw = data.get("full_response") if isinstance(data.get("full_response"), dict) else data
        return {
            "state_name": str(raw.get("StateName") or data.get("state") or ""),
            "plate_number": str(data.get("plate_number") or raw.get("PlateNumber") or ""),
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
        values = self._repository_values(session)
        try:
            session.repository_id = await asyncio.to_thread(
                self.repository.create, values
            )
            if self.repository_mode == "sql":
                self.persistence_available = True
                self.persistence_error = None
        except Exception as exc:
            error = self._persistence_error(exc)
            self._switch_to_memory(error)
            session.repository_id = await asyncio.to_thread(
                self.repository.create, values
            )
            logger.error("Lidar SQL persistence unavailable; session continues in memory: %s", error)

    async def _update_repository(self, session: ActiveLidarPass) -> None:
        if session.repository_id is None:
            return
        try:
            await asyncio.to_thread(
                self.repository.update,
                session.repository_id,
                self._repository_values(session),
            )
            if self.repository_mode == "sql":
                self.persistence_available = True
                self.persistence_error = None
        except Exception as exc:
            error = self._persistence_error(exc)
            values = self._repository_values(session)
            self._switch_to_memory(error)
            session.repository_id = await asyncio.to_thread(self.repository.create, values)
            logger.error("Lidar SQL update failed; session copied to memory: %s", error)

    def _sync_profiles(self, session: ActiveLidarPass) -> None:
        if not session.recording:
            return
        new_profiles = self.buffer.profiles_after(session.last_sequence_number)
        if new_profiles:
            session.profiles.extend(new_profiles)
            session.last_sequence_number = new_profiles[-1].sequence_number

    def _log_fsm(self, session: ActiveLidarPass, snapshot: dict) -> None:
        values = (
            session.session_key,
            snapshot["state_name"],
            snapshot["massa"],
            snapshot["stabil"],
            self._stable_samples,
        )
        if values == self._last_logged_fsm:
            return
        logger.info(
            "SCALE_FSM session=%s state=%s massa=%s stabil=%s stable_count=%s/%s",
            session.session_key,
            snapshot["state_name"],
            snapshot["massa"],
            snapshot["stabil"],
            self._stable_samples,
            self.stable_confirm_samples,
        )
        self._last_logged_fsm = values

    def _reset_stable_counter(
        self, reason: str, session: ActiveLidarPass, snapshot: dict
    ) -> None:
        self._stable_samples = 0
        self._last_stable_reset_reason = reason
        logger.info(
            "stable counter reset session=%s reason=%s", session.session_key, reason
        )
        self._log_fsm(session, snapshot)
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
        self._current_lifecycle_token = session.session_key
        self._last_logged_fsm = None
        self._reset_stable_counter("new_session", session, snapshot)
        await self._create_repository_record(session)

    async def _finish_after_delay(self, session_key: str) -> None:
        await asyncio.sleep(self.post_stable_seconds)
        async with self._lock:
            session = self.active_session
            if session is None or session.session_key != session_key or not session.recording:
                return
            self._sync_profiles(session)
            await self._finalize_active_session(session)

    async def _finalize_active_session(
        self, session: ActiveLidarPass, *, reason: Optional[str] = None
    ) -> None:
        """Finish, persist and detach a pass exactly once. Caller holds ``_lock``."""
        if not session.recording or self.active_session is not session:
            return
        self._sync_profiles(session)
        finished_at = utc_now()
        session.ended_at = finished_at
        session.completed_at = finished_at
        session.workflow_state = "COMPLETED"
        session.state_timestamps["COMPLETED"] = finished_at.isoformat()
        if not session.profiles:
            session.status = "FAILED"
            session.error_message = reason or self.buffer.last_error or "lidar_profiles_unavailable"
            await self._update_repository(session)
        else:
            session.status = "COMPLETED"
            if session.stable_weight_at is None:
                session.stable_weight_kg = session.maximum_observed_weight_kg
                session.error_message = reason or "stable_weight_missing"
            metadata = self._repository_values(session)
            metadata.update({
                "session_key": session.session_key,
                "started_at": session.started_at.isoformat(),
                "load_scale_at": session.load_scale_at.isoformat(),
                "stable_weight_at": session.stable_weight_at.isoformat() if session.stable_weight_at else None,
                "ended_at": session.ended_at.isoformat(),
                "completed_at": session.completed_at.isoformat(),
            })
            try:
                session.data_file_path = await asyncio.to_thread(
                    self.storage.save, metadata, [profile.to_dict() for profile in session.profiles]
                )
            except Exception as exc:
                session.status = "FAILED"
                session.error_message = f"json_write_failed:{type(exc).__name__}: {exc}"
            await self._update_repository(session)
        self.last_session = session
        self.active_session = None
        self._stable_samples = 0
        self._empty_samples = 0
        self._seen_unload = False
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
                self._last_stable_sample_at = now
                self._log_fsm(session, snapshot)
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

                if state_name in {"ReadyWeighing", "WeighingComplete"} and session.recording:
                    reset_reason = (
                        "ready_weighing" if state_name == "ReadyWeighing" else "weighing_complete"
                    )
                    if session.stable_weight_at is None:
                        logger.warning(
                            "fallback finalize without stable weight session=%s state=%s stable_count=%s/%s",
                            session.session_key,
                            state_name,
                            self._stable_samples,
                            self.stable_confirm_samples,
                        )
                    self._reset_stable_counter(reset_reason, session, snapshot)
                    await self._finalize_active_session(
                        session, reason="stable_weight_missing" if session.stable_weight_at is None else None
                    )
                    self._previous_state_name = state_name
                    return

                if state_name == "Weighing" and snapshot["stabil"] and session.stable_weight_at is None:
                    self._stable_samples += 1
                    logger.info(
                        "stable counter increment session=%s stable_count=%s/%s",
                        session.session_key,
                        self._stable_samples,
                        self.stable_confirm_samples,
                    )
                    self._log_fsm(session, snapshot)
                    if self._stable_samples >= self.stable_confirm_samples:
                        session.stable_weight_at = now
                        session.stable_weight_kg = snapshot["massa"]
                        session.workflow_state = "WEIGHT_CAPTURED"
                        session.state_timestamps["WEIGHT_CAPTURED"] = now.isoformat()
                        logger.info(
                            "stable weight confirmed session=%s massa=%s stable_count=%s/%s",
                            session.session_key,
                            snapshot["massa"],
                            self._stable_samples,
                            self.stable_confirm_samples,
                        )
                        self._finish_task = asyncio.create_task(
                            self._finish_after_delay(session.session_key),
                            name="lidar-post-stable-finish",
                        )
                elif session.stable_weight_at is None:
                    reset_reason = (
                        "stabil_false" if state_name == "Weighing" else "state_not_weighing"
                    )
                    self._reset_stable_counter(reset_reason, session, snapshot)

                if state_name == "UnLoadScale":
                    self._seen_unload = True
                if (
                    state_name == "Empty"
                    and snapshot["stabil"]
                    and snapshot["massa"] <= self.empty_threshold_kg
                ):
                    self._empty_samples += 1
                    if self._empty_samples >= self.empty_confirm_samples:
                        if session.stable_weight_at is None:
                            logger.warning(
                                "fallback finalize without stable weight session=%s state=%s stable_count=%s/%s",
                                session.session_key, state_name, self._stable_samples, self.stable_confirm_samples,
                            )
                        self._reset_stable_counter("empty", session, snapshot)
                        await self._finalize_active_session(
                            session,
                            reason="Session ended without stable weight"
                            if session.stable_weight_at is None and not session.profiles
                            else None,
                        )
                else:
                    self._empty_samples = 0

            self._previous_state_name = state_name

    def current_pass_token(self) -> Optional[str]:
        return self._current_lifecycle_token

    def bound_trip_id(self, pass_token: Optional[str]) -> Optional[int]:
        if not pass_token or pass_token != self._current_lifecycle_token:
            return None
        for session in (self.active_session, self.last_session):
            if session is not None and session.session_key == pass_token:
                return session.trip_id
        return None

    async def bind_trip(self, trip_id: int, pass_token: Optional[str] = None) -> bool:
        async with self._lock:
            if not pass_token:
                logger.warning("Lidar trip bind rejected: trip_id=%s reason=missing_pass_token", trip_id)
                return False
            if pass_token != self._current_lifecycle_token:
                logger.warning(
                    "Lidar trip bind rejected: trip_id=%s pass_token=%s current_token=%s reason=stale_lifecycle",
                    trip_id,
                    pass_token,
                    self._current_lifecycle_token,
                )
                return False
            session = next(
                (
                    candidate
                    for candidate in (self.active_session, self.last_session)
                    if candidate is not None and candidate.session_key == pass_token
                ),
                None,
            )
            if session is None:
                logger.warning(
                    "Lidar trip bind rejected: trip_id=%s pass_token=%s reason=session_not_found",
                    trip_id,
                    pass_token,
                )
                return False
            if session.trip_id == trip_id:
                return True
            if session.trip_id is not None:
                logger.error(
                    "Lidar trip rebind rejected: session=%s existing_trip_id=%s requested_trip_id=%s",
                    session.session_key,
                    session.trip_id,
                    trip_id,
                )
                return False
            session.trip_id = trip_id
            await self._update_repository(session)
            logger.info("Lidar session bound: session=%s trip_id=%s", session.session_key, trip_id)
            return True
    def current_state(self) -> dict:
        session = self.active_session
        snapshot = self.last_scale_snapshot or {}
        return {
            "scale": {
                "state_name": snapshot.get("state_name"),
                "plate_number": snapshot.get("plate_number"),
                "massa": snapshot.get("massa"),
                "stabil": snapshot.get("stabil"),
                "connected": self.scale_connected,
            },
            "lidar": {
                **self.buffer.status(),
                "recording": bool(session and session.recording),
                "session_profiles": len(session.profiles) if session else 0,
            },
            "active_session": self._session_state(self.active_session),
            "stable_confirmation": {
                "current_count": self._stable_samples,
                "required_count": self.stable_confirm_samples,
                "last_reset_reason": self._last_stable_reset_reason,
                "last_sample_at": self._last_stable_sample_at.isoformat()
                if self._last_stable_sample_at
                else None,
            },
            "persistence_available": self.persistence_available,
            "persistence_error": self.persistence_error,
            "repository_mode": self.repository_mode,
        }

    def session_state(self) -> Optional[dict]:
        return self._session_state(self.active_session or self.last_session)

    @staticmethod
    def _session_state(session: Optional[ActiveLidarPass]) -> Optional[dict]:
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
