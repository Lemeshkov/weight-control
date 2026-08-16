
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
        def current_pass_token(self):
            return None

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

def test_new_entry_does_not_reuse_old_active_trip(monkeypatch):
    old_trip = scale_monitor_module.models.Trip(
        id=7,
        vehicle_id=1,
        status=scale_monitor_module.models.TripStatus.ENTRY,
    )
    added = []

    class FakeDb:
        def add(self, value):
            added.append(value)

        def flush(self):
            trip = next(
                value
                for value in added
                if isinstance(value, scale_monitor_module.models.Trip)
            )
            trip.id = 8

        def commit(self):
            return None

        def rollback(self):
            raise AssertionError("entry creation unexpectedly rolled back")

        def close(self):
            return None

    class CoordinatorSpy:
        def bound_trip_id(self, pass_token):
            assert pass_token == "new-pass"
            return None

        async def bind_trip(self, trip_id, pass_token, **identity):
            assert (trip_id, pass_token) == (8, "new-pass")
            assert identity == {
                "vehicle_id": 1,
                "license_plate_snapshot": "A001AA",
                "uniserver_code": None,
            }
            return True

    monkeypatch.setattr(scale_monitor_module, "SessionLocal", FakeDb)
    monkeypatch.setattr(
        scale_monitor_module.VehicleCRUD,
        "get_or_create_by_plate",
        lambda db, plate: type("Vehicle", (), {"id": 1})(),
    )
    monkeypatch.setattr(
        scale_monitor_module.TripCRUD,
        "get_trip_by_vehicle_and_status",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("old active trip lookup must not be used for entry")
        ),
    )
    monkeypatch.setattr(
        scale_monitor_module, "weighing_lidar_coordinator", CoordinatorSpy()
    )

    asyncio.run(
        scale_monitor_module.ScaleMonitor()._handle_entry(
            "A001AA", 4850, {"doc_id": ""}, "new-pass"
        )
    )

    new_trip = next(
        value
        for value in added
        if isinstance(value, scale_monitor_module.models.Trip)
    )
    assert new_trip.id == 8
    assert new_trip.status == scale_monitor_module.models.TripStatus.ENTRY
    assert old_trip.id == 7
    assert old_trip.status == scale_monitor_module.models.TripStatus.ENTRY

def test_restart_existing_trip_does_not_bind_without_lifecycle_token(monkeypatch, caplog):
    existing_trip = scale_monitor_module.models.Trip(
        id=10,
        vehicle_id=1,
        status=scale_monitor_module.models.TripStatus.ENTRY,
        uniserver_code="DOC-10",
    )
    bind_calls = []

    class FakeQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return existing_trip

    class FakeDb:
        def query(self, _model):
            return FakeQuery()

        def rollback(self):
            raise AssertionError("existing trip lookup unexpectedly rolled back")

        def close(self):
            return None

    class CoordinatorSpy:
        def bound_trip_id(self, pass_token):
            assert pass_token is None
            return None

        async def bind_trip(self, trip_id, pass_token):
            bind_calls.append((trip_id, pass_token))

    monkeypatch.setattr(scale_monitor_module, "SessionLocal", FakeDb)
    monkeypatch.setattr(
        scale_monitor_module.VehicleCRUD,
        "get_or_create_by_plate",
        lambda db, plate: type("Vehicle", (), {"id": 1})(),
    )
    monkeypatch.setattr(
        scale_monitor_module, "weighing_lidar_coordinator", CoordinatorSpy()
    )

    asyncio.run(
        scale_monitor_module.ScaleMonitor()._handle_entry(
            "A001AA", 4850, {"doc_id": "DOC-10"}, None
        )
    )

    assert bind_calls == []
    assert existing_trip.id == 10
    assert "missing_pass_token" not in caplog.text
