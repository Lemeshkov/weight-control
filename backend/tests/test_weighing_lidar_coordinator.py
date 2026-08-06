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

    session = coordinator.last_session
    assert coordinator.active_session is None
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
    assert coordinator.last_session.trip_id == 7
    assert coordinator.last_session.status == "FAILED"
    assert coordinator.last_session.error_message == "lidar_profiles_unavailable"


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
    assert coordinator.last_session.status == "FAILED"
    assert coordinator.last_session.error_message.startswith("json_write_failed:OSError")


def test_ready_without_stable_finalizes_with_diagnostic_weight(tmp_path):
    coordinator, buffer, _ = make_coordinator(tmp_path)
    buffer.add_profile([100], captured_at=datetime.now(timezone.utc))

    async def scenario():
        await coordinator.on_scale_snapshot(snapshot("LoadScale", 500, False))
        await coordinator.on_scale_snapshot(snapshot("Weighing", 1800, False))
        await coordinator.on_scale_snapshot(snapshot("ReadyWeighing", 1750, False))

    asyncio.run(scenario())
    session = coordinator.last_session
    assert coordinator.active_session is None
    assert session.status == "COMPLETED"
    assert session.workflow_state == "COMPLETED"
    assert session.stable_weight_at is None
    assert session.stable_weight_kg == 1800
    assert session.error_message == "stable_weight_missing"
    assert session.ended_at is not None
    assert session.completed_at is not None
    assert session.data_file_path


def test_empty_fallback_is_idempotent_and_current_has_no_active_session(tmp_path):
    coordinator, buffer, _ = make_coordinator(tmp_path)
    buffer.add_profile([100], captured_at=datetime.now(timezone.utc))

    async def scenario():
        await coordinator.on_scale_snapshot(snapshot("LoadScale", 500, False))
        await coordinator.on_scale_snapshot(snapshot("UnLoadScale", 100, False))
        await coordinator.on_scale_snapshot(snapshot("Empty", 0, True))
        first_path = coordinator.last_session.data_file_path
        await coordinator.on_scale_snapshot(snapshot("Empty", 0, True))
        return first_path

    first_path = asyncio.run(scenario())
    assert coordinator.current_state()["active_session"] is None
    assert coordinator.session_state()["status"] == "COMPLETED"
    assert coordinator.session_state()["data_file_path"] == first_path
    assert len(list(tmp_path.glob("lidar_pass_*.json"))) == 1


def test_profiles_are_not_added_after_finalize(tmp_path):
    coordinator, buffer, _ = make_coordinator(tmp_path, stable_samples=1, post_delay=0)
    buffer.add_profile([100], captured_at=datetime.now(timezone.utc))

    async def scenario():
        await coordinator.on_scale_snapshot(snapshot("LoadScale", 500, False))
        await coordinator.on_scale_snapshot(snapshot("Weighing", 1000, True))
        await coordinator._finish_task
        count = len(coordinator.last_session.profiles)
        buffer.add_profile([200], captured_at=datetime.now(timezone.utc))
        await coordinator.on_scale_snapshot(snapshot("Empty", 0, True))
        return count

    count = asyncio.run(scenario())
    assert len(coordinator.last_session.profiles) == count


def test_three_identical_stable_samples_confirm_weight_and_are_logged(tmp_path, caplog):
    coordinator, buffer, _ = make_coordinator(tmp_path, stable_samples=3, post_delay=60)
    buffer.add_profile([100], captured_at=datetime.now(timezone.utc))

    async def scenario():
        await coordinator.on_scale_snapshot(snapshot("LoadScale", 500, False))
        for _ in range(3):
            await coordinator.on_scale_snapshot(snapshot("Weighing", 1700, True))

    with caplog.at_level("INFO"):
        asyncio.run(scenario())
    assert coordinator.active_session.stable_weight_kg == 1700
    assert "stable counter increment" in caplog.text
    assert "stable weight confirmed" in caplog.text
    assert "stable_count=3/3" in caplog.text
    asyncio.run(coordinator.stop())


def test_change_only_forwarding_exposes_missing_confirmation(tmp_path):
    coordinator, buffer, _ = make_coordinator(tmp_path, stable_samples=3)
    buffer.add_profile([100], captured_at=datetime.now(timezone.utc))
    samples = [snapshot("Weighing", 1700, True) for _ in range(3)]

    async def scenario():
        await coordinator.on_scale_snapshot(snapshot("LoadScale", 500, False))
        previous = None
        for item in samples:
            normalized = coordinator._normalise_snapshot(item)
            comparable = (normalized["state_name"], normalized["massa"], normalized["stabil"])
            if comparable != previous:
                await coordinator.on_scale_snapshot(item)
                previous = comparable

    asyncio.run(scenario())
    assert coordinator._stable_samples == 1
    assert coordinator.active_session.stable_weight_at is None


def test_ready_after_two_samples_reports_missing_stable_weight(tmp_path, caplog):
    coordinator, buffer, _ = make_coordinator(tmp_path, stable_samples=3)
    buffer.add_profile([100], captured_at=datetime.now(timezone.utc))

    async def scenario():
        await coordinator.on_scale_snapshot(snapshot("LoadScale", 500, False))
        await coordinator.on_scale_snapshot(snapshot("Weighing", 1700, True))
        await coordinator.on_scale_snapshot(snapshot("Weighing", 1700, True))
        await coordinator.on_scale_snapshot(snapshot("ReadyWeighing", 1700, True))

    with caplog.at_level("INFO"):
        asyncio.run(scenario())
    assert coordinator.last_session.error_message == "stable_weight_missing"
    assert "fallback finalize without stable weight" in caplog.text
    assert "stable_count=2/3" in caplog.text
    assert "reason=ready_weighing" in caplog.text


def test_stabil_false_resets_counter_with_diagnostic_state(tmp_path, caplog):
    coordinator, buffer, _ = make_coordinator(tmp_path, stable_samples=3)
    buffer.add_profile([100], captured_at=datetime.now(timezone.utc))

    async def scenario():
        await coordinator.on_scale_snapshot(snapshot("LoadScale", 500, False))
        await coordinator.on_scale_snapshot(snapshot("Weighing", 1700, True))
        await coordinator.on_scale_snapshot(snapshot("Weighing", 1700, False))

    with caplog.at_level("INFO"):
        asyncio.run(scenario())
    assert coordinator._stable_samples == 0
    assert coordinator.current_state()["stable_confirmation"]["last_reset_reason"] == "stabil_false"
    assert coordinator.current_state()["stable_confirmation"]["last_sample_at"] is not None
    assert "reason=stabil_false" in caplog.text


def test_stable_confirm_samples_is_read_from_environment(monkeypatch):
    import os
    import subprocess
    import sys

    environment = os.environ.copy()
    environment["SCALE_STABLE_CONFIRM_SAMPLES"] = "7"
    result = subprocess.run(
        [sys.executable, "-c", "from config import settings; print(settings.SCALE_STABLE_CONFIRM_SAMPLES)"],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "7"