import asyncio
from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import models
from database import Base
from routers.control import get_control_history


def test_control_history_uses_bounded_queries_and_latest_lidar_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    carrier = models.Carrier(name="Test")
    vehicle = models.Vehicle(plate_number="A123BC", model="Ural", carrier=carrier)
    trip = models.Trip(vehicle=vehicle, entry_time=datetime.now(), status=models.TripStatus.ENTRY)
    trip.entry_measurement = models.EntryMeasurement(weight_brutto=4850)
    common = dict(status="COMPLETED", workflow_state="COMPLETED", trigger_type="LOAD_SCALE", trigger_state_name="LoadScale", load_scale_at=datetime.now(timezone.utc), pre_trigger_seconds=5, pre_trigger_profiles_count=10, profiles_count=20, valid_profiles_count=18, points_total=100, points_valid=90, weight_samples_count=3, state_timestamps={}, volume_status="NOT_CALCULATED")
    trip.lidar_pass_sessions = [
        models.LidarPassSession(started_at=datetime(2026, 1, 1, tzinfo=timezone.utc), **common),
        models.LidarPassSession(started_at=datetime(2026, 1, 2, tzinfo=timezone.utc), profiles_count=37, **{key: value for key, value in common.items() if key != "profiles_count"}),
    ]
    session.add(trip)
    session.commit()
    selects = []
    event.listen(engine, "before_cursor_execute", lambda _c, _x, statement, _p, _ctx, _many: selects.append(statement) if statement.lstrip().upper().startswith("SELECT") else None)

    response = asyncio.run(get_control_history(limit=50, db=session))

    assert len(selects) == 2
    assert response["items"][0]["lidar"]["profiles_count"] == 37
    assert "distances_mm" not in str(response)


def test_control_history_supports_trip_without_lidar():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    vehicle = models.Vehicle(plate_number="B456CC")
    session.add(models.Trip(vehicle=vehicle, entry_time=datetime.now(), status=models.TripStatus.ENTRY))
    session.commit()

    response = asyncio.run(get_control_history(limit=50, db=session))

    assert response["items"][0]["lidar"] is None
