import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy.exc import ProgrammingError

from routers import control
from services.lidar_pass_storage import AtomicLidarPassStorage
from services.lidar_profile_buffer import LidarProfileBuffer
from services.lidar_session_repository import (
    InMemoryLidarSessionRepository,
    SqlAlchemyLidarSessionRepository,
)
from services.weighing_lidar_coordinator import WeighingLidarCoordinator


class FakeLidarClient:
    is_connected = True


class MissingTableRepository(SqlAlchemyLidarSessionRepository):
    def __init__(self):
        self.create_calls = 0

    def is_available(self):
        return False

    def create(self, values):
        self.create_calls += 1
        raise AssertionError("SQL INSERT must not run after startup fallback")


class FailedTransactionSession:
    def __init__(self):
        self.rollback_calls = 0
        self.close_calls = 0
        self.events = []

    def add(self, record):
        self.record = record

    def commit(self):
        self.events.append("commit")
        raise ProgrammingError(
            "INSERT INTO lidar_pass_sessions",
            {},
            Exception('relation "lidar_pass_sessions" does not exist'),
        )

    def rollback(self):
        self.rollback_calls += 1
        self.events.append("rollback")

    def close(self):
        self.close_calls += 1
        self.events.append("close")


def scale(state_name, massa=0, stabil=False):
    return {
        "full_response": {
            "StateName": state_name,
            "State": 2,
            "Massa": massa,
            "Stabil": stabil,
            "Enable": True,
        }
    }


def coordinator_for(tmp_path, repository, memory_repository=None):
    buffer = LidarProfileBuffer(FakeLidarClient(), buffer_seconds=5, max_count=100)
    coordinator = WeighingLidarCoordinator(
        buffer=buffer,
        repository=repository,
        memory_repository=memory_repository,
        storage=AtomicLidarPassStorage(str(tmp_path / "lidar_passes")),
        stable_confirm_samples=1,
        post_stable_seconds=0,
        empty_confirm_samples=1,
    )
    return coordinator, buffer


def add_pretrigger(buffer, count=2):
    for index in range(count):
        buffer.add_profile(
            [100 + index, 200 + index],
            captured_at=datetime.now(timezone.utc),
        )


def test_missing_table_at_startup_selects_memory_without_insert(tmp_path):
    sql = MissingTableRepository()
    coordinator, buffer = coordinator_for(tmp_path, sql)
    add_pretrigger(buffer)

    async def scenario():
        assert await coordinator.check_persistence() is False
        await coordinator.on_scale_snapshot(scale("LoadScale", 1600))

    asyncio.run(scenario())
    assert coordinator.repository_mode == "memory"
    assert sql.create_calls == 0
    assert coordinator.active_session is not None


def test_programming_error_rolls_back_and_retries_create_in_memory(tmp_path):
    failed_db = FailedTransactionSession()
    sql = SqlAlchemyLidarSessionRepository(session_factory=lambda: failed_db)
    memory = InMemoryLidarSessionRepository()
    coordinator, buffer = coordinator_for(tmp_path, sql, memory)
    add_pretrigger(buffer)

    asyncio.run(coordinator.on_scale_snapshot(scale("LoadScale", 1600)))

    assert failed_db.rollback_calls == 1
    assert failed_db.close_calls == 1
    assert failed_db.events == ["commit", "rollback", "close"]
    assert coordinator.repository_mode == "memory"
    assert coordinator.active_session.repository_id == 1
    assert memory.get(1)["status"] == "RECORDING"


def test_pretrigger_profiles_survive_repository_fallback(tmp_path):
    coordinator, buffer = coordinator_for(tmp_path, MissingTableRepository())
    add_pretrigger(buffer, 15)

    async def scenario():
        await coordinator.check_persistence()
        await coordinator.on_scale_snapshot(scale("LoadScale", 1600))

    asyncio.run(scenario())
    assert coordinator.active_session.pre_trigger_profiles_count == 15
    assert len(coordinator.active_session.profiles) == 15


def test_stable_weight_completes_session_in_memory_mode(tmp_path):
    coordinator, buffer = coordinator_for(tmp_path, MissingTableRepository())
    add_pretrigger(buffer)

    async def scenario():
        await coordinator.check_persistence()
        await coordinator.on_scale_snapshot(scale("LoadScale", 1600))
        await coordinator.on_scale_snapshot(scale("Weighing", 31520, True))
        await coordinator._finish_task

    asyncio.run(scenario())
    assert coordinator.last_session.status == "COMPLETED"
    assert coordinator.last_session.stable_weight_kg == 31520


def test_json_is_created_without_postgresql_table(tmp_path):
    coordinator, buffer = coordinator_for(tmp_path, MissingTableRepository())
    add_pretrigger(buffer)

    async def scenario():
        await coordinator.check_persistence()
        await coordinator.on_scale_snapshot(scale("LoadScale", 1600))
        await coordinator.on_scale_snapshot(scale("Weighing", 31520, True))
        await coordinator._finish_task

    asyncio.run(scenario())
    path = coordinator.last_session.data_file_path
    assert path is not None
    with open(path, encoding="utf-8") as saved:
        payload = json.load(saved)
    assert payload["session"]["status"] == "COMPLETED"
    assert len(payload["profiles"]) == 2


def test_api_returns_memory_session_and_unavailable_persistence(tmp_path, monkeypatch):
    coordinator, buffer = coordinator_for(tmp_path, MissingTableRepository())
    add_pretrigger(buffer)

    async def scenario():
        await coordinator.check_persistence()
        await coordinator.on_scale_snapshot(scale("LoadScale", 1600))
        monkeypatch.setattr(control, "weighing_lidar_coordinator", coordinator)
        return await control.get_current_lidar_session()

    response = asyncio.run(scenario())
    assert response["session"]["status"] == "RECORDING"
    assert response["persistence_available"] is False
    assert response["persistence_error"] == "lidar_pass_sessions table is missing"
    assert response["repository_mode"] == "memory"


def test_updates_do_not_retry_sql_after_fallback(tmp_path):
    sql = MissingTableRepository()
    coordinator, buffer = coordinator_for(tmp_path, sql)
    add_pretrigger(buffer)

    async def scenario():
        await coordinator.check_persistence()
        await coordinator.on_scale_snapshot(scale("LoadScale", 1600))
        await coordinator.bind_trip(42, coordinator.current_pass_token())
        await coordinator.on_scale_snapshot(scale("Weighing", 31520, True))
        await coordinator._finish_task

    asyncio.run(scenario())
    assert sql.create_calls == 0
    assert coordinator.repository_mode == "memory"


def test_next_pass_gets_a_separate_memory_session(tmp_path):
    coordinator, buffer = coordinator_for(tmp_path, MissingTableRepository())
    add_pretrigger(buffer)

    async def scenario():
        await coordinator.check_persistence()
        await coordinator.on_scale_snapshot(scale("LoadScale", 1600))
        first_key = coordinator.active_session.session_key
        first_id = coordinator.active_session.repository_id
        await coordinator.on_scale_snapshot(scale("Weighing", 31520, True))
        await coordinator._finish_task
        await coordinator.on_scale_snapshot(scale("UnLoadScale", 200))
        await coordinator.on_scale_snapshot(scale("Empty", 0, True))
        assert coordinator.active_session is None
        assert coordinator.session_state()["session_key"] == first_key
        await coordinator.on_scale_snapshot(scale("LoadScale", 1700))
        return first_key, first_id

    first_key, first_id = asyncio.run(scenario())
    assert coordinator.active_session.session_key != first_key
    assert coordinator.active_session.repository_id != first_id
