import asyncio

import pytest
from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from fastapi import FastAPI
from fastapi.testclient import TestClient

import database

import models
from database import Base
from routers.control import get_control_history, router as control_router


def lidar_values(*, started_at, profiles_count=25, pre_trigger_profiles_count=15):
    return dict(
        status="COMPLETED",
        workflow_state="COMPLETED",
        trigger_type="LOAD_SCALE",
        trigger_state_name="LoadScale",
        started_at=started_at,
        load_scale_at=started_at,
        stable_weight_at=started_at,
        ended_at=started_at,
        completed_at=started_at,
        pre_trigger_seconds=5,
        pre_trigger_profiles_count=pre_trigger_profiles_count,
        profiles_count=profiles_count,
        valid_profiles_count=profiles_count,
        points_total=100,
        points_valid=90,
        weight_samples_count=3,
        state_timestamps={},
        volume_status="NOT_CALCULATED",
    )


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine)()


def test_control_history_returns_bound_completed_lidar_for_real_scenario():
    engine, session = make_session()
    trip = models.Trip(
        id=10,
        vehicle=models.Vehicle(plate_number="У211АА147"),
        entry_time=datetime(2026, 8, 7, 14, 17, 47),
        status=models.TripStatus.ENTRY,
    )
    trip.entry_measurement = models.EntryMeasurement(weight_brutto=4850)
    lidar = models.LidarPassSession(
        id=2,
        trip_id=10,
        **lidar_values(
            started_at=datetime(2026, 8, 7, 7, 17, 41, tzinfo=timezone.utc)
        ),
    )
    session.add(trip)
    session.commit()
    assert trip.lidar_pass_sessions == []
    repository_session = sessionmaker(bind=engine)()
    repository_session.add(lidar)
    repository_session.commit()
    repository_session.close()

    response = asyncio.run(get_control_history(limit=10, db=session))

    item = next(item for item in response["items"] if item["trip_id"] == 10)
    assert item["lidar"] is not None
    assert item["lidar"]["session_id"] == 2
    assert item["lidar"]["status"] == "COMPLETED"
    assert item["lidar"]["profiles_count"] == 25
    assert item["lidar"]["pre_trigger_profiles_count"] == 15
    assert item["lidar"]["volume_status"] == "NOT_CALCULATED"
    assert item["lidar"]["estimated_volume_m3"] is None
    assert item["lidar"]["error_message"] is None
    assert item["sessions_count"] == 1


def test_control_history_uses_latest_session_and_ignores_orphan():
    _engine, session = make_session()
    trip = models.Trip(
        id=10,
        vehicle=models.Vehicle(plate_number="A123BC"),
        entry_time=datetime.now(),
        status=models.TripStatus.ENTRY,
    )
    older = models.LidarPassSession(
        id=1,
        trip_id=10,
        **lidar_values(
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            profiles_count=20,
        ),
    )
    latest = models.LidarPassSession(
        id=2,
        trip_id=10,
        **lidar_values(
            started_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            profiles_count=37,
        ),
    )
    orphan = models.LidarPassSession(
        id=3,
        trip_id=None,
        **lidar_values(
            started_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
            profiles_count=99,
        ),
    )
    session.add_all([trip, older, latest, orphan])
    session.commit()

    response = asyncio.run(get_control_history(limit=50, db=session))

    item = response["items"][0]
    assert item["lidar"]["session_id"] == 2
    assert item["lidar"]["profiles_count"] == 37
    assert item["sessions_count"] == 2


def test_control_history_supports_multiple_trips_and_trip_without_lidar():
    _engine, session = make_session()
    with_lidar = models.Trip(
        id=10,
        vehicle=models.Vehicle(plate_number="A123BC"),
        entry_time=datetime(2026, 1, 1, 12),
        status=models.TripStatus.ENTRY,
    )
    without_lidar = models.Trip(
        id=11,
        vehicle=models.Vehicle(plate_number="B456CC"),
        entry_time=datetime(2026, 1, 2, 12),
        status=models.TripStatus.ENTRY,
    )
    session.add_all(
        [
            with_lidar,
            without_lidar,
            models.LidarPassSession(
                trip_id=10,
                **lidar_values(started_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
            ),
        ]
    )
    session.commit()

    response = asyncio.run(get_control_history(limit=50, db=session))
    items = {item["trip_id"]: item for item in response["items"]}

    assert items[10]["lidar"] is not None
    assert items[10]["sessions_count"] == 1
    assert items[11]["lidar"] is None
    assert items[11]["sessions_count"] == 0


def test_control_history_query_count_is_constant():
    engine, session = make_session()
    for trip_id in range(1, 6):
        trip = models.Trip(
            id=trip_id,
            vehicle=models.Vehicle(plate_number=f"TEST{trip_id}"),
            entry_time=datetime(2026, 1, trip_id),
            status=models.TripStatus.ENTRY,
        )
        session.add(trip)
        session.add(
            models.LidarPassSession(
                trip_id=trip_id,
                **lidar_values(started_at=datetime(2026, 1, trip_id, tzinfo=timezone.utc)),
            )
        )
    session.commit()
    selects = []
    event.listen(
        engine,
        "before_cursor_execute",
        lambda _c, _x, statement, _p, _ctx, _many: selects.append(statement)
        if statement.lstrip().upper().startswith("SELECT")
        else None,
    )

    response = asyncio.run(get_control_history(limit=50, db=session))

    assert len(response["items"]) == 5
    assert len(selects) == 2
    assert "distances_mm" not in str(response)


def test_control_history_server_side_pages_total_and_stable_order():
    _engine, session = make_session()
    for trip_id in range(1, 26):
        session.add(models.Trip(id=trip_id, vehicle=models.Vehicle(plate_number=f"P{trip_id}"), entry_time=datetime(2026, 1, 1), status=models.TripStatus.ENTRY))
    session.commit()
    first = asyncio.run(get_control_history(limit=50, page=1, page_size=10, db=session))
    middle = asyncio.run(get_control_history(limit=50, page=2, page_size=10, db=session))
    last = asyncio.run(get_control_history(limit=50, page=3, page_size=10, db=session))
    beyond = asyncio.run(get_control_history(limit=50, page=4, page_size=10, db=session))
    assert (first['total'],first['total_pages'])==(25,3)
    assert [x['trip_id'] for x in first['items']]==list(range(25,15,-1))
    assert [x['trip_id'] for x in middle['items']]==list(range(15,5,-1))
    assert [x['trip_id'] for x in last['items']]==list(range(5,0,-1))
    assert beyond['items']==[] and beyond['total']==25


def test_control_history_empty_paginated_journal():
    _engine, session = make_session()
    response = asyncio.run(get_control_history(limit=50, page=1, page_size=10, db=session))
    assert response == {'items': [], 'total': 0, 'page': 1, 'page_size': 10, 'total_pages': 0}


@pytest.mark.parametrize("acceptance_status", [None, models.CoalAcceptanceStatus.DRAFT, models.CoalAcceptanceStatus.COMPLETED])
def test_control_history_http_endpoint_uses_production_get_db_session_factory(
    tmp_path, monkeypatch, acceptance_status
):
    database_path = tmp_path / "control-history.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    test_session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
    monkeypatch.setattr(database, "SessionLocal", test_session_factory)

    db = test_session_factory()
    trip = models.Trip(
        id=10,
        vehicle=models.Vehicle(plate_number="У211АА147"),
        entry_time=datetime(2026, 8, 7, 14, 17, 47),
        status=models.TripStatus.ENTRY,
    )
    trip.entry_measurement = models.EntryMeasurement(weight_brutto=4850)
    if acceptance_status is not None:
        trip.coal_acceptance = models.CoalAcceptance(status=acceptance_status)
    db.add_all(
        [
            trip,
            models.LidarPassSession(
                id=2,
                trip_id=10,
                **lidar_values(
                    started_at=datetime(2026, 8, 7, 7, 17, 41, tzinfo=timezone.utc)
                ),
            ),
        ]
    )
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(control_router)
    response = TestClient(app).get("/api/control/history?limit=10")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["trip_id"] == 10
    assert item["acceptance_status"] == (
        acceptance_status.value if acceptance_status else "WAITING"
    )
    assert item["sessions_count"] == 1
    assert item["lidar"] is not None
    assert item["lidar"]["session_id"] == 2
    assert item["lidar"]["profiles_count"] == 25
