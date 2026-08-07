from datetime import datetime
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

import models
from database import get_db
from services.lidar_profile_buffer import lidar_profile_buffer
from services.weighing_lidar_coordinator import weighing_lidar_coordinator


router = APIRouter(prefix="/api/control", tags=["control"])


class ControlHistoryVehicle(BaseModel):
    brand: Optional[str] = None
    license_plate: str


class ControlHistoryWeight(BaseModel):
    value_kg: Optional[float] = None
    tare_kg: Optional[float] = None
    net_kg: Optional[float] = None
    stable: bool
    completed_at: Optional[datetime] = None


class ControlHistoryLidar(BaseModel):
    session_id: int
    session_key: Optional[str] = None
    status: str
    workflow_state: str
    started_at: datetime
    load_scale_at: datetime
    stable_weight_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    stable_weight_kg: Optional[float] = None
    maximum_observed_weight_kg: Optional[float] = None
    profiles_count: int
    pre_trigger_profiles_count: int
    valid_profiles_count: int
    points_total: int
    points_valid: int
    data_file_path: Optional[str] = None
    error_message: Optional[str] = None
    volume_status: str
    estimated_volume_m3: Optional[float] = None


class ControlHistoryItem(BaseModel):
    trip_id: int
    entry_time: datetime
    exit_time: Optional[datetime] = None
    status: str
    vehicle: ControlHistoryVehicle
    weight: ControlHistoryWeight
    lidar: Optional[ControlHistoryLidar] = None
    sessions_count: int = 0
    photo_path: Optional[str] = None
    acceptance_status: str = "WAITING"


class ControlHistoryResponse(BaseModel):
    items: list[ControlHistoryItem]


@router.get("/current")
async def get_current_control_state():
    return weighing_lidar_coordinator.current_state()


@router.get("/lidar-buffer/status")
async def get_lidar_buffer_status():
    return lidar_profile_buffer.status()


@router.get("/lidar-sessions/current")
async def get_current_lidar_session():
    return {
        "session": weighing_lidar_coordinator.session_state(),
        "persistence_available": weighing_lidar_coordinator.persistence_available,
        "persistence_error": weighing_lidar_coordinator.persistence_error,
        "repository_mode": getattr(weighing_lidar_coordinator, "repository_mode", "unknown"),
    }


@router.get("/history", response_model=ControlHistoryResponse)
async def get_control_history(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    trips = (
        db.query(models.Trip)
        .options(
            joinedload(models.Trip.vehicle),
            joinedload(models.Trip.entry_measurement),
            joinedload(models.Trip.exit_measurement),
            joinedload(models.Trip.coal_acceptance),
        )
        .order_by(models.Trip.entry_time.desc())
        .limit(limit)
        .all()
    )
    trip_ids = [trip.id for trip in trips]
    sessions_by_trip: dict[int, list[models.LidarPassSession]] = defaultdict(list)
    if trip_ids:
        lidar_sessions = (
            db.query(models.LidarPassSession)
            .filter(models.LidarPassSession.trip_id.in_(trip_ids))
            .order_by(
                models.LidarPassSession.trip_id,
                models.LidarPassSession.started_at.desc(),
                models.LidarPassSession.id.desc(),
            )
            .all()
        )
        for session in lidar_sessions:
            if session.trip_id is not None:
                sessions_by_trip[int(session.trip_id)].append(session)
    items = []
    for trip in trips:
        trip_sessions = sessions_by_trip.get(int(trip.id), [])
        latest_lidar = trip_sessions[0] if trip_sessions else None
        brutto = trip.entry_measurement.weight_brutto if trip.entry_measurement else None
        tare = trip.exit_measurement.weight_tare if trip.exit_measurement else None
        item = {
                "trip_id": trip.id,
                "entry_time": trip.entry_time,
                "exit_time": trip.exit_time,
                "status": trip.status.value if hasattr(trip.status, "value") else str(trip.status),
                "vehicle": {
                    "brand": trip.vehicle.model if trip.vehicle else None,
                    "license_plate": trip.vehicle.plate_number if trip.vehicle else "вЂ”",
                },
                "weight": {
                    "value_kg": brutto,
                    "tare_kg": tare,
                    "net_kg": brutto - tare if brutto is not None and tare is not None else None,
                    "stable": bool(latest_lidar and latest_lidar.stable_weight_at),
                    "completed_at": latest_lidar.completed_at if latest_lidar else trip.exit_time,
                },
                "lidar": {
                    "session_id": latest_lidar.id,
                    "session_key": None,
                    "status": latest_lidar.status,
                    "workflow_state": latest_lidar.workflow_state,
                    "started_at": latest_lidar.started_at,
                    "load_scale_at": latest_lidar.load_scale_at,
                    "stable_weight_at": latest_lidar.stable_weight_at,
                    "ended_at": latest_lidar.ended_at,
                    "stable_weight_kg": latest_lidar.stable_weight_kg,
                    "maximum_observed_weight_kg": latest_lidar.maximum_observed_weight_kg,
                    "profiles_count": latest_lidar.profiles_count,
                    "pre_trigger_profiles_count": latest_lidar.pre_trigger_profiles_count,
                    "valid_profiles_count": latest_lidar.valid_profiles_count,
                    "points_total": latest_lidar.points_total,
                    "points_valid": latest_lidar.points_valid,
                    "data_file_path": latest_lidar.data_file_path,
                    "error_message": latest_lidar.error_message,
                    "volume_status": latest_lidar.volume_status,
                    "estimated_volume_m3": latest_lidar.estimated_volume_m3,
                } if latest_lidar else None,
                "sessions_count": len(trip_sessions),
                "photo_path": (
                    trip.entry_measurement.photo_path
                    if trip.entry_measurement and trip.entry_measurement.photo_path
                    else trip.exit_measurement.photo_path
                    if trip.exit_measurement and trip.exit_measurement.photo_path
                    else None
                ),
            }
        item["acceptance_status"] = (
            trip.coal_acceptance.status.value
            if trip.coal_acceptance else "WAITING"
        )
        items.append(item)
    return {"items": items}
