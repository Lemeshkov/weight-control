from fastapi import APIRouter

from services.lidar_profile_buffer import lidar_profile_buffer
from services.weighing_lidar_coordinator import weighing_lidar_coordinator


router = APIRouter(prefix="/api/control", tags=["control"])


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
