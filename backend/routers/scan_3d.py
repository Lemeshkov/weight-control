# backend/routers/scan_3d.py
"""
3D сканирование для измерения объёма угля в движении
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime
from typing import List, Dict, Optional
import logging
import time
import uuid
from sqlalchemy.orm import Session
from database import get_db
from models import LidarMeasurement

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scan3d", tags=["3d-scan"])

# Хранилище активных сессий (в продакшене использовать Redis)
active_sessions: Dict[str, Dict] = {}


# ========== Pydantic модели ==========

class StartScanRequest(BaseModel):
    truck_length_m: float = 6.0
    truck_width_m: float = 2.5
    coal_density_kg_m3: float = 850


class StartScanResponse(BaseModel):
    scan_id: str
    status: str
    message: str


class AddProfileRequest(BaseModel):
    scan_id: str
    distances_mm: List[int]
    position_m: float


class AddProfileResponse(BaseModel):
    status: str
    profile_count: int
    current_position_m: float
    current_volume_m3: Optional[float] = None


class ScanResult(BaseModel):
    scan_id: str
    total_volume_m3: float
    total_mass_tons: float
    profiles_count: int
    truck_length_m: float
    truck_width_m: float
    duration_seconds: float
    status: str


# ========== Вспомогательные функции ==========

def calculate_cross_section(distances_mm: List[int], width_m: float) -> float:
    """Рассчитывает площадь поперечного сечения по одному профилю"""
    if not distances_mm:
        return 0.0
    
    road_level = max(distances_mm) / 1000
    heights = []
    
    for d in distances_mm:
        dist_m = d / 1000
        if dist_m < road_level - 0.03:
            heights.append(road_level - dist_m)
        else:
            heights.append(0)
    
    valid_heights = [h for h in heights if h > 0.01]
    if not valid_heights:
        return 0.0
    
    avg_height = sum(valid_heights) / len(valid_heights)
    return avg_height * width_m


def calculate_total_volume(profiles: List[Dict]) -> float:
    """Рассчитывает интегральный объём методом трапеций"""
    if len(profiles) < 2:
        return 0.0
    
    total_volume = 0.0
    for i in range(1, len(profiles)):
        dx = profiles[i]["position_m"] - profiles[i-1]["position_m"]
        avg_area = (profiles[i-1]["cross_section_m2"] + profiles[i]["cross_section_m2"]) / 2
        total_volume += avg_area * dx
    
    return total_volume


# ========== API эндпоинты ==========

@router.post("/start", response_model=StartScanResponse)
async def start_3d_scan(request: StartScanRequest):
    """Начать новую сессию 3D сканирования"""
    scan_id = str(uuid.uuid4())[:8]
    
    active_sessions[scan_id] = {
        "started_at": datetime.now(),
        "profiles": [],
        "truck_length_m": request.truck_length_m,
        "truck_width_m": request.truck_width_m,
        "coal_density_kg_m3": request.coal_density_kg_m3,
        "status": "scanning",
        "current_position_m": 0.0
    }
    
    logger.info(f"🚀 Начато 3D сканирование: {scan_id}, длина={request.truck_length_m}м")
    
    return StartScanResponse(
        scan_id=scan_id,
        status="scanning",
        message="3D scan started. Move the truck slowly through the scanner."
    )


@router.post("/add-profile", response_model=AddProfileResponse)
async def add_scan_profile(request: AddProfileRequest):
    """Добавить один профиль к сессии сканирования"""
    if request.scan_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Scan session not found")
    
    session = active_sessions[request.scan_id]
    
    if session["status"] != "scanning":
        raise HTTPException(status_code=400, detail="Scan session is not active")
    
    # Рассчитываем сечение
    cross_section = calculate_cross_section(
        request.distances_mm, 
        session["truck_width_m"]
    )
    
    # Добавляем профиль
    profile = {
        "timestamp": time.time(),
        "position_m": request.position_m,
        "distances_mm": request.distances_mm,
        "cross_section_m2": cross_section
    }
    
    session["profiles"].append(profile)
    session["current_position_m"] = request.position_m
    
    # Рассчитываем текущий объём
    current_volume = calculate_total_volume(session["profiles"])
    
    logger.debug(f"📊 Профиль #{len(session['profiles'])}, "
                f"позиция={request.position_m:.2f}м, "
                f"сечение={cross_section:.3f}м², "
                f"объём={current_volume:.3f}м³")
    
    return AddProfileResponse(
        status="ok",
        profile_count=len(session["profiles"]),
        current_position_m=request.position_m,
        current_volume_m3=round(current_volume, 3)
    )


@router.post("/stop", response_model=ScanResult)
async def stop_3d_scan(
    scan_id: str,
    db: Session = Depends(get_db)  # ← ДОБАВИТЬ ЗАВИСИМОСТЬ БД
):
    """Остановить сканирование, рассчитать объём и сохранить в БД"""
    if scan_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Scan session not found")
    
    session = active_sessions[scan_id]
    profiles = session["profiles"]
    
    if len(profiles) < 2:
        raise HTTPException(
            status_code=400, 
            detail=f"Not enough profiles: {len(profiles)}. Need at least 2."
        )
    
    # Рассчитываем итоговый объём
    total_volume = calculate_total_volume(profiles)
    total_mass_tons = (total_volume * session["coal_density_kg_m3"]) / 1000
    duration = (datetime.now() - session["started_at"]).total_seconds()
    
    # ✅ СОХРАНЯЕМ РЕЗУЛЬТАТ В БД
    measurement = LidarMeasurement(
        timestamp=datetime.now(),
        points_count=len(profiles),
        distances_mm=[],  # 3D не хранит все точки (экономия памяти)
        distances_m=[],
        volume_m3=round(total_volume, 3),
        mass_tons=round(total_mass_tons, 2),
        avg_height_m=0,
        cross_section_m2=0,
        truck_length_m=session["truck_length_m"],
        truck_width_m=session["truck_width_m"],
        coal_density_kg_m3=session["coal_density_kg_m3"],
        is_empty=total_volume < 0.1
    )
    
    db.add(measurement)
    db.commit()
    db.refresh(measurement)
    
    logger.info(f"✅ 3D измерение сохранено в БД: ID={measurement.id}, объём={total_volume:.3f}м³")
    
    result = ScanResult(
        scan_id=scan_id,
        total_volume_m3=round(total_volume, 3),
        total_mass_tons=round(total_mass_tons, 2),
        profiles_count=len(profiles),
        truck_length_m=session["truck_length_m"],
        truck_width_m=session["truck_width_m"],
        duration_seconds=round(duration, 1),
        status="completed"
    )
    
    session["status"] = "completed"
    session["result"] = result.dict()
    
    return result


@router.get("/status/{scan_id}")
async def get_scan_status(scan_id: str):
    """Получить статус сканирования"""
    if scan_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Scan session not found")
    
    session = active_sessions[scan_id]
    
    return {
        "scan_id": scan_id,
        "status": session["status"],
        "profiles_count": len(session["profiles"]),
        "current_position_m": session["current_position_m"],
        "started_at": session["started_at"].isoformat(),
        "truck_length_m": session["truck_length_m"],
        "truck_width_m": session["truck_width_m"]
    }


@router.get("/profiles/{scan_id}")
async def get_scan_profiles(scan_id: str, limit: int = 200):
    """Получить профили для визуализации"""
    if scan_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Scan session not found")
    
    session = active_sessions[scan_id]
    profiles = session["profiles"][-limit:] if limit > 0 else session["profiles"]
    
    return {
        "scan_id": scan_id,
        "profiles": [
            {
                "position": p["position_m"],
                "cross_section": p["cross_section_m2"],
                "timestamp": p["timestamp"]
            }
            for p in profiles
        ],
        "total_profiles": len(session["profiles"]),
        "total_volume": calculate_total_volume(session["profiles"]) if session["profiles"] else 0
    }


@router.delete("/{scan_id}")
async def delete_scan_session(scan_id: str):
    """Удалить сессию сканирования (очистить память)"""
    if scan_id in active_sessions:
        del active_sessions[scan_id]
        logger.info(f"🗑️ Удалена сессия сканирования: {scan_id}")
        return {"status": "deleted", "scan_id": scan_id}
    
    raise HTTPException(status_code=404, detail="Scan session not found")