import asyncio
import json
from datetime import datetime, timezone

from services.lidar_pass_storage import AtomicLidarPassStorage
from services.lidar_profile_buffer import LidarProfileBuffer
from services.lidar_session_repository import InMemoryLidarSessionRepository
from services.weighing_lidar_coordinator import WeighingLidarCoordinator


class FakeLidarClient:
    is_connected = True


class FailingStorage:
    def save(self, session, profiles):
        raise OSError("disk unavailable")


def snapshot(state_name, massa=0, stabil=False):
    return {
        "full_response": {
            "StateName": state_name,
            "State": 2,
            "Massa": massa,
            "Stabil": stabil,
            "Enable": True,
        }
    }


def make_coordinator(tmp_path, *, stable_samples=3, post_delay=0.01, storage=None):
    buffer = LidarProfileBuffer(client=FakeLidarClient(), buffer_seconds=5, max_count=100)
    repository = InMemoryLidarSessionRepository()
    coordinator = WeighingLidarCoordinator(
        buffer=buffer,
        repository=repository,
        storage=storage or AtomicLidarPassStorage(str(tmp_path)),
        stable_confirm_samples=stable_samples,
        post_stable_seconds=post_delay,
        empty_confirm_samples=1,
    )
    return coordinator, buffer, repository


def test_load_scale_opens_one_session_with_pretrigger_profiles(tmp_path):
    coordinator, buffer, _ = make_coordinator(tmp_path)
    buffer.add_profile([100, 200], captured_at=datetime.now(timezone.utc))
    buffer.add_profile([300, 400], captured_at=datetime.now(timezone.utc))

    async def scenario():
        await coordinator.on_scale_snapshot(snapshot("LoadScale", 1300, False))
        first_key = coordinator.active_session.session_key
        await coordinator.on_scale_snapshot(snapshot("LoadScale", 1310, False))
        return first_key

    first_key = asyncio.run(scenario())

    assert coordinator.active_session.session_key == first_key
    assert coordinator.active_session.pre_trigger_profiles_count == 2
    assert len(coordinator.active_session.profiles) == 2
    assert coordinator.active_session.trip_id is None
    assert coordinator.active_session.status == "RECORDING"


def test_stable_weight_requires_confirmations_and_closes_after_delay(tmp_path):
    coordinator, buffer, _ = make_coordinator(tmp_path, stable_samples=3, post_delay=0.01)
    buffer.add_profile([100, 200], captured_at=datetime.now(timezone.utc))

    async def scenario():
        await coordinator.on_scale_snapshot(snapshot("LoadScale", 1000, False))
        await coordinator.on_scale_snapshot(snapshot("Weighing", 1500, True))
        await coordinator.on_scale_snapshot(snapshot("Weighing", 1500, True))
        assert coordinator.active_session.stable_weight_at is None
        await coordinator.on_scale_snapshot(snapshot("Weighing", 1500, True))
        assert coordinator.active_session.stable_weight_at is not None
        await coordinator._finish_task

    asyncio.run(scenario())

    session = coordinator.active_session
    assert session.status == "COMPLETED"
    assert session.ended_at is not None
    assert session.stable_weight_kg == 1500
    assert session.data_file_path
    with open(session.data_file_path, encoding="utf-8") as saved:
        payload = json.load(saved)
    assert payload["session"]["volume_status"] == "NOT_CALCULATED"
    assert payload["session"]["estimated_volume_m3"] is None
    assert len(payload["profiles"]) >= 1


def test_short_stability_pulse_is_reset(tmp_path):
    coordinator, buffer, _ = make_coordinator(tmp_path, stable_samples=3)
    buffer.add_profile([100], captured_at=datetime.now(timezone.utc))

    async def scenario():
        await coordinator.on_scale_snapshot(snapshot("LoadScale", 1000, False))
        await coordinator.on_scale_snapshot(snapshot("Weighing", 1200, True))
        await coordinator.on_scale_snapshot(snapshot("Weighing", 1200, False))
        await coordinator.on_scale_snapshot(snapshot("Weighing", 1200, True))

    asyncio.run(scenario())
    assert coordinator.active_session.stable_weight_at is None


def test_trip_binding_is_idempotent(tmp_path):
    coordinator, buffer, repository = make_coordinator(tmp_path)
    buffer.add_profile([100], captured_at=datetime.now(timezone.utc))

    async def scenario():
        await coordinator.on_scale_snapshot(snapshot("LoadScale", 500, False))
        assert await coordinator.bind_trip(42) is True
        assert await coordinator.bind_trip(42) is True
        assert await coordinator.bind_trip(43) is False

    asyncio.run(scenario())
    session = coordinator.active_session
    assert session.trip_id == 42
    assert repository.get(session.repository_id)["trip_id"] == 42


def test_missing_lidar_profiles_does_not_raise_in_scale_flow(tmp_path):
    coordinator, _, _ = make_coordinator(tmp_path, stable_samples=1, post_delay=0.01)

    async def scenario():
        await coordinator.on_scale_snapshot(snapshot("LoadScale", 500, False))
        await coordinator.on_scale_snapshot(snapshot("Weighing", 1000, True))
        assert await coordinator.bind_trip(7) is True
        await coordinator._finish_task

    asyncio.run(scenario())
    assert coordinator.active_session.trip_id == 7
    assert coordinator.active_session.status == "FAILED"
    assert coordinator.active_session.error_message == "lidar_profiles_unavailable"


def test_json_write_error_marks_session_failed(tmp_path):
    coordinator, buffer, _ = make_coordinator(
        tmp_path,
        stable_samples=1,
        post_delay=0.01,
        storage=FailingStorage(),
    )
    buffer.add_profile([100], captured_at=datetime.now(timezone.utc))

    async def scenario():
        await coordinator.on_scale_snapshot(snapshot("LoadScale", 500, False))
        await coordinator.on_scale_snapshot(snapshot("Weighing", 1000, True))
        await coordinator._finish_task

    asyncio.run(scenario())
    assert coordinator.active_session.status == "FAILED"
    assert coordinator.active_session.error_message.startswith("json_write_failed:OSError")
