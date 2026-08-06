
import asyncio

from services import scale_monitor as scale_monitor_module


def test_scale_monitor_forwards_identical_snapshots(monkeypatch):
    data = {
        "full_response": {"StateName": "Weighing", "Massa": 1700, "Stabil": True},
        "plate_number": "",
        "weight": 1700,
        "is_stable": True,
    }
    calls = []

    async def get_current_weighting():
        return data

    class CoordinatorSpy:
        async def on_scale_snapshot(self, value):
            calls.append(value)

        async def on_scale_unavailable(self):
            raise AssertionError("scale unexpectedly unavailable")

    monkeypatch.setattr(
        scale_monitor_module.uniserver_client,
        "get_current_weighting",
        get_current_weighting,
    )
    monkeypatch.setattr(
        scale_monitor_module, "weighing_lidar_coordinator", CoordinatorSpy()
    )
    monitor = scale_monitor_module.ScaleMonitor()

    async def scenario():
        await monitor.check_scale()
        await monitor.check_scale()
        await monitor.check_scale()

    asyncio.run(scenario())
    assert calls == [data, data, data]