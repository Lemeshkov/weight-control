import asyncio
from datetime import datetime, timedelta, timezone

from services.lidar_profile_buffer import LidarProfileBuffer


class FakeLidarClient:
    def __init__(self):
        self.is_connected = True
        self.read_count = 0

    def get_scan_data(self):
        self.read_count += 1
        return "raw"

    def parse_raw_data(self, raw_data):
        return [100, 200, 300, 400]

    def filter_angle(self, values, angle):
        return values

    def filter_valid_distances(self, values):
        return values


def test_buffer_is_bounded_by_time_and_count():
    current = [datetime(2026, 8, 5, tzinfo=timezone.utc)]
    buffer = LidarProfileBuffer(
        client=FakeLidarClient(),
        buffer_seconds=5,
        max_count=3,
        clock=lambda: current[0],
    )

    for value in range(4):
        buffer.add_profile([value], captured_at=current[0])
        current[0] += timedelta(seconds=1)

    assert [profile.distances_mm for profile in buffer.profiles()] == [[1], [2], [3]]

    current[0] += timedelta(seconds=6)
    assert buffer.profiles() == []


def test_capture_once_is_the_only_socket_read():
    client = FakeLidarClient()
    buffer = LidarProfileBuffer(client=client)

    profile = asyncio.run(buffer.capture_once())

    assert profile is not None
    assert client.read_count == 1
    assert buffer.latest_raw_data() == "raw"
    assert buffer.status()["buffer_profiles"] == 1


def test_read_only_state_calls_do_not_read_socket():
    client = FakeLidarClient()
    buffer = LidarProfileBuffer(client=client)
    buffer.add_profile([100, 200], raw_data="cached")

    async def read_concurrently():
        await asyncio.gather(*[asyncio.to_thread(buffer.status) for _ in range(20)])

    asyncio.run(read_concurrently())

    assert client.read_count == 0
    assert buffer.latest_raw_data() == "cached"


def test_parallel_control_api_reads_do_not_touch_socket(monkeypatch):
    from routers import control

    client = FakeLidarClient()
    buffer = LidarProfileBuffer(client=client)
    buffer.add_profile([100], raw_data="cached")

    class FakeCoordinator:
        persistence_available = True
        persistence_error = None

        def current_state(self):
            return {"lidar": buffer.status()}

        def session_state(self):
            return None

    monkeypatch.setattr(control, "lidar_profile_buffer", buffer)
    monkeypatch.setattr(control, "weighing_lidar_coordinator", FakeCoordinator())

    async def scenario():
        await asyncio.gather(
            *[control.get_current_control_state() for _ in range(10)],
            *[control.get_lidar_buffer_status() for _ in range(10)],
            *[control.get_current_lidar_session() for _ in range(10)],
        )

    asyncio.run(scenario())
    assert client.read_count == 0
