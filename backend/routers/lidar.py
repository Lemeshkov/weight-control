# # backend/routers/lidar.py
# from fastapi import APIRouter, HTTPException, Depends
# from datetime import datetime
# import logging
# from services.lidar_client import LidarClient
# from sqlalchemy.orm import Session
# from database import get_db
# import time
# from models import LidarMeasurement
# from pydantic import BaseModel
# from typing import Optional, List

# logger = logging.getLogger(__name__)
# router = APIRouter(prefix="/api/lidar", tags=["lidar"])

# lidar_client = LidarClient(host="192.168.1.101", port=2111)


# class SingleScanRequest(BaseModel):
#     trip_id: Optional[int] = None
#     truck_length_m: float = 6.0
#     truck_width_m: float = 2.5
#     coal_density_kg_m3: float = 850


# @router.on_event("startup")
# async def startup_lidar():
#     try:
#         if lidar_client.connect():
#             logger.info("✅ Лидар подключен")
#             configure_lidar_angle()
#         else:
#             logger.warning("⚠️ Лидар не подключен")
#     except Exception as e:
#         logger.error(f"❌ Ошибка: {e}")


# def configure_lidar_angle():
#     try:
#         if not lidar_client.sock or not lidar_client.is_connected:
#             return False
        
#         commands = [
#             "sWN LMPoutputRange 1 5000 -3500 3500",
#             "sWN LMPoutputRange 1 +5000 -3500 +3500",
#         ]
        
#         for cmd in commands:
#             logger.info(f"Пробуем: {cmd}")
#             result = lidar_client._send_raw(cmd)
#             logger.info(f"Результат: {result}")
#             time.sleep(0.2)
        
#         lidar_client._send_raw("sMN Logout")
#         time.sleep(0.2)
#         lidar_client._send_raw("sMN SetAccessMode 3 F4724744")
#         time.sleep(0.2)
#         lidar_client._send_raw("sMN Run")
#         time.sleep(0.2)
        
#         logger.info("✅ Угол сканирования настроен: -35°...+35° (70°)")
#         return True
#     except Exception as e:
#         logger.error(f"❌ Ошибка настройки угла: {e}")
#         return False


# @router.on_event("shutdown")
# async def shutdown_lidar():
#     if lidar_client.is_connected:
#         lidar_client.disconnect()


# @router.get("/scan")
# async def get_lidar_scan():
#     """Получить данные сканирования (без сохранения)"""
#     if not lidar_client.is_connected:
#         if not lidar_client.connect():
#             raise HTTPException(status_code=503, detail="Лидар не подключен")
    
#     scan_data = lidar_client.get_scan_data()
#     if not scan_data:
#         raise HTTPException(status_code=500, detail="Не удалось получить данные")
    
#     parsed = lidar_client.parse_scan_data(scan_data, filter_angle=True, separate_object=False)
    
#     return {
#         "timestamp": datetime.now().isoformat(),
#         "points_count": parsed.get("points_count", 0),
#         "distances_mm": parsed.get("distances_mm", []),
#         "distances_m": parsed.get("distances_m", []),
#         "statistics": {
#             "min_mm": parsed.get("min_distance_mm"),
#             "max_mm": parsed.get("max_distance_mm"),
#             "avg_mm": parsed.get("avg_distance_mm"),
#             "min_m": parsed.get("min_distance_m"),
#             "max_m": parsed.get("max_distance_m"),
#             "avg_m": parsed.get("avg_distance_m")
#         }
#     }


# @router.get("/status")
# async def get_lidar_status():
#     return {
#         "connected": lidar_client.is_connected,
#         "host": "192.168.1.101",
#         "port": 2111
#     }


# @router.post("/measure")
# async def measure_and_save(
#     request: SingleScanRequest,
#     db: Session = Depends(get_db)
# ):
#     """Выполнить одно сканирование и сохранить в БД"""
#     if not lidar_client.is_connected:
#         if not lidar_client.connect():
#             raise HTTPException(status_code=503, detail="Лидар не подключен")
    
#     scan_data = lidar_client.get_scan_data()
#     if not scan_data:
#         raise HTTPException(status_code=500, detail="Не удалось получить данные")
    
#     parsed = lidar_client.parse_scan_data(scan_data, filter_angle=True, separate_object=False)
#     distances_mm = parsed.get("distances_mm", [])
    
#     if not distances_mm:
#         raise HTTPException(status_code=400, detail="Нет данных в скане")
    
#     # Расчёт объёма
#     roadLevel = max(distances_mm) / 1000
#     heights = []
#     for d in distances_mm:
#         distM = d / 1000
#         if distM < roadLevel - 0.03:
#             heights.append(roadLevel - distM)
#         else:
#             heights.append(0)
    
#     validHeights = [h for h in heights if h > 0.01]
    
#     if validHeights:
#         avgHeight = sum(validHeights) / len(validHeights)
#         volume_m3 = request.truck_length_m * request.truck_width_m * avgHeight
#         mass_tons = (volume_m3 * request.coal_density_kg_m3) / 1000
#         cross_section = avgHeight * request.truck_width_m
#         is_empty = len(distances_mm) < 15
#     else:
#         volume_m3 = 0
#         mass_tons = 0
#         cross_section = 0
#         avgHeight = 0
#         is_empty = True
    
#     measurement = LidarMeasurement(
#         timestamp=datetime.now(),
#         trip_id=request.trip_id,
#         points_count=len(distances_mm),
#         distances_mm=distances_mm,
#         distances_m=[d/1000 for d in distances_mm],
#         volume_m3=round(volume_m3, 3),
#         mass_tons=round(mass_tons, 2),
#         avg_height_m=round(avgHeight, 2),
#         cross_section_m2=round(cross_section, 3),
#         truck_length_m=request.truck_length_m,
#         truck_width_m=request.truck_width_m,
#         coal_density_kg_m3=request.coal_density_kg_m3,
#         is_empty=is_empty,
#         empty_confidence=95 if is_empty else 0
#     )
    
#     db.add(measurement)
#     db.commit()
#     db.refresh(measurement)
    
#     logger.info(f"✅ Измерение сохранено: ID={measurement.id}, объём={volume_m3:.3f}м³")
    
#     return {
#         "id": measurement.id,
#         "timestamp": measurement.timestamp.isoformat(),
#         "points_count": measurement.points_count,
#         "volume_m3": measurement.volume_m3,
#         "mass_tons": measurement.mass_tons,
#         "avg_height_m": measurement.avg_height_m,
#         "cross_section_m2": measurement.cross_section_m2,
#         "is_empty": measurement.is_empty,
#         "distances_mm": measurement.distances_mm
#     }


# @router.get("/measurements")
# async def get_measurements(
#     limit: int = 50,
#     skip: int = 0,
#     db: Session = Depends(get_db)
# ):
#     measurements = db.query(LidarMeasurement).order_by(
#         LidarMeasurement.timestamp.desc()
#     ).offset(skip).limit(limit).all()
    
#     return [
#         {
#             "id": m.id,
#             "timestamp": m.timestamp.isoformat(),
#             "points_count": m.points_count,
#             "volume_m3": m.volume_m3,
#             "mass_tons": m.mass_tons,
#             "avg_height_m": m.avg_height_m,
#             "cross_section_m2": m.cross_section_m2,
#             "is_empty": m.is_empty
#         }
#         for m in measurements
#     ]


# @router.get("/measurements/{measurement_id}")
# async def get_measurement(measurement_id: int, db: Session = Depends(get_db)):
#     measurement = db.query(LidarMeasurement).filter(LidarMeasurement.id == measurement_id).first()
#     if not measurement:
#         raise HTTPException(status_code=404, detail="Измерение не найдено")
    
#     return {
#         "id": measurement.id,
#         "timestamp": measurement.timestamp.isoformat(),
#         "points_count": measurement.points_count,
#         "distances_mm": measurement.distances_mm,
#         "distances_m": measurement.distances_m,
#         "volume_m3": measurement.volume_m3,
#         "mass_tons": measurement.mass_tons,
#         "avg_height_m": measurement.avg_height_m,
#         "cross_section_m2": measurement.cross_section_m2,
#         "is_empty": measurement.is_empty
#     }


# @router.get("/angle")
# async def get_lidar_angle():
#     if not lidar_client.is_connected:
#         if not lidar_client.connect():
#             raise HTTPException(status_code=503, detail="Лидар не подключен")
    
#     angle_info = lidar_client.get_current_angle_range()
    
#     if not angle_info:
#         return {"status": "error", "message": "Не удалось получить информацию об угле"}
    
#     return {
#         "status": "ok",
#         "current": angle_info,
#         "target": {
#             "start_angle_deg": -35.0,
#             "stop_angle_deg": 35.0,
#             "total_angle_deg": 70.0
#         }
#     }
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
import logging
from services.lidar_client import LidarClient
from sqlalchemy.orm import Session
from database import get_db
import time
from models import LidarMeasurement
from pydantic import BaseModel
from typing import Optional, List
from services.vehicle_profiles import vehicle_profiles, VehicleProfile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/lidar", tags=["lidar"])

lidar_client = LidarClient(host="192.168.1.101", port=2111)


class SingleScanRequest(BaseModel):
    trip_id: Optional[int] = None
    truck_length_m: float = 6.0
    truck_width_m: float = 2.5
    coal_density_kg_m3: float = 850


@router.on_event("startup")
async def startup_lidar():
    try:
        if lidar_client.connect():
            logger.info("✅ Лидар подключен")
            configure_lidar_angle()
        else:
            logger.warning("⚠️ Лидар не подключен")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")


def configure_lidar_angle():
    try:
        if not lidar_client.sock or not lidar_client.is_connected:
            return False
        
        commands = [
            "sWN LMPoutputRange 1 5000 -3500 3500",
            "sWN LMPoutputRange 1 +5000 -3500 +3500",
        ]
        
        for cmd in commands:
            logger.info(f"Пробуем: {cmd}")
            result = lidar_client._send_raw(cmd)
            logger.info(f"Результат: {result}")
            time.sleep(0.2)
        
        lidar_client._send_raw("sMN Logout")
        time.sleep(0.2)
        lidar_client._send_raw("sMN SetAccessMode 3 F4724744")
        time.sleep(0.2)
        lidar_client._send_raw("sMN Run")
        time.sleep(0.2)
        
        logger.info("✅ Угол сканирования настроен: -35°...+35° (70°)")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка настройки угла: {e}")
        return False


@router.on_event("shutdown")
async def shutdown_lidar():
    if lidar_client.is_connected:
        lidar_client.disconnect()


@router.get("/scan")
async def get_lidar_scan():
    """Получить данные сканирования с детекцией объекта"""
    if not lidar_client.is_connected:
        if not lidar_client.connect():
            raise HTTPException(status_code=503, detail="Лидар не подключен")
    
    scan_data = lidar_client.get_scan_data()
    if not scan_data:
        raise HTTPException(status_code=500, detail="Не удалось получить данные")
    
    # ✅ Включаем отделение объекта от пола
    parsed = lidar_client.parse_scan_data(
        scan_data, 
        filter_angle=True, 
        separate_object=True,  # ← ВКЛЮЧАЕМ детекцию объекта
        mode="auto"  # ← Автоопределение режима (коробка/грузовик)
    )
    
    return {
        "timestamp": datetime.now().isoformat(),
        "points_count": parsed.get("points_count", 0),
        "distances_mm": parsed.get("distances_mm", []),
        "distances_m": parsed.get("distances_m", []),
        "is_empty": parsed.get("is_empty", True),
        "empty_confidence": parsed.get("empty_confidence", 0),
        "empty_reason": parsed.get("empty_reason", ""),
        "object_type": parsed.get("object_type", "unknown"),
        "object_height_mm": parsed.get("object_height_mm", 0),
        "floor_level_mm": parsed.get("floor_level_mm", 0),
        "statistics": {
            "min_mm": parsed.get("min_distance_mm"),
            "max_mm": parsed.get("max_distance_mm"),
            "avg_mm": parsed.get("avg_distance_mm"),
            "min_m": parsed.get("min_distance_m"),
            "max_m": parsed.get("max_distance_m"),
            "avg_m": parsed.get("avg_distance_m")
        }
    }


@router.get("/status")
async def get_lidar_status():
    return {
        "connected": lidar_client.is_connected,
        "host": "192.168.1.101",
        "port": 2111
    }


@router.post("/measure")
async def measure_and_save(
    request: SingleScanRequest,
    db: Session = Depends(get_db)
):
    """Выполнить одно сканирование и сохранить в БД"""
    if not lidar_client.is_connected:
        if not lidar_client.connect():
            raise HTTPException(status_code=503, detail="Лидар не подключен")
    
    scan_data = lidar_client.get_scan_data()
    if not scan_data:
        raise HTTPException(status_code=500, detail="Не удалось получить данные")
    
    # ✅ Включаем детекцию объекта для анализа пустоты
    parsed = lidar_client.parse_scan_data(
        scan_data, 
        filter_angle=True, 
        separate_object=True,
        mode="auto"
    )
    
    distances_mm = parsed.get("distances_mm", [])
    
    if not distances_mm:
        raise HTTPException(status_code=400, detail="Нет данных в скане")
    
    # Используем данные из детектора
    is_empty = parsed.get("is_empty", True)
    empty_confidence = parsed.get("empty_confidence", 0)
    empty_reason = parsed.get("empty_reason", "")
    object_type = parsed.get("object_type", "unknown")
    object_height_mm = parsed.get("object_height_mm", 0)
    
    # Расчёт объёма (только если не пусто)
    if not is_empty and distances_mm:
        roadLevel = parsed.get("floor_level_mm", max(distances_mm)) / 1000
        heights = []
        for d in distances_mm:
            distM = d / 1000
            if distM < roadLevel - 0.03:
                heights.append(roadLevel - distM)
            else:
                heights.append(0)
        
        validHeights = [h for h in heights if h > 0.01]
        
        if validHeights:
            avgHeight = sum(validHeights) / len(validHeights)
            # Используем высоту объекта из детектора если она больше
            if object_height_mm / 1000 > avgHeight:
                avgHeight = object_height_mm / 1000
            
            volume_m3 = request.truck_length_m * request.truck_width_m * avgHeight
            mass_tons = (volume_m3 * request.coal_density_kg_m3) / 1000
            cross_section = avgHeight * request.truck_width_m
        else:
            volume_m3 = 0
            mass_tons = 0
            cross_section = 0
            avgHeight = 0
    else:
        volume_m3 = 0
        mass_tons = 0
        cross_section = 0
        avgHeight = 0
    
    measurement = LidarMeasurement(
        timestamp=datetime.now(),
        trip_id=request.trip_id,
        points_count=len(distances_mm),
        distances_mm=distances_mm,
        distances_m=[d/1000 for d in distances_mm],
        volume_m3=round(volume_m3, 3),
        mass_tons=round(mass_tons, 2),
        avg_height_m=round(avgHeight, 2),
        cross_section_m2=round(cross_section, 3),
        truck_length_m=request.truck_length_m,
        truck_width_m=request.truck_width_m,
        coal_density_kg_m3=request.coal_density_kg_m3,
        is_empty=is_empty,
        empty_confidence=empty_confidence,
        empty_reason=empty_reason  # Добавьте это поле в модель
    )
    
    db.add(measurement)
    db.commit()
    db.refresh(measurement)
    
    logger.info(f"✅ Измерение сохранено: ID={measurement.id}, объём={volume_m3:.3f}м³, пусто={is_empty}")
    
    return {
        "id": measurement.id,
        "timestamp": measurement.timestamp.isoformat(),
        "points_count": measurement.points_count,
        "volume_m3": measurement.volume_m3,
        "mass_tons": measurement.mass_tons,
        "avg_height_m": measurement.avg_height_m,
        "cross_section_m2": measurement.cross_section_m2,
        "is_empty": measurement.is_empty,
        "empty_confidence": measurement.empty_confidence,
        "empty_reason": empty_reason,
        "object_type": object_type,
        "distances_mm": measurement.distances_mm
    }


@router.get("/measurements")
async def get_measurements(
    limit: int = 50,
    skip: int = 0,
    db: Session = Depends(get_db)
):
    measurements = db.query(LidarMeasurement).order_by(
        LidarMeasurement.timestamp.desc()
    ).offset(skip).limit(limit).all()
    
    return [
        {
            "id": m.id,
            "timestamp": m.timestamp.isoformat(),
            "points_count": m.points_count,
            "volume_m3": m.volume_m3,
            "mass_tons": m.mass_tons,
            "avg_height_m": m.avg_height_m,
            "cross_section_m2": m.cross_section_m2,
            "is_empty": m.is_empty,
            "empty_confidence": m.empty_confidence
        }
        for m in measurements
    ]


@router.get("/measurements/{measurement_id}")
async def get_measurement(measurement_id: int, db: Session = Depends(get_db)):
    measurement = db.query(LidarMeasurement).filter(LidarMeasurement.id == measurement_id).first()
    if not measurement:
        raise HTTPException(status_code=404, detail="Измерение не найдено")
    
    return {
        "id": measurement.id,
        "timestamp": measurement.timestamp.isoformat(),
        "points_count": measurement.points_count,
        "distances_mm": measurement.distances_mm,
        "distances_m": measurement.distances_m,
        "volume_m3": measurement.volume_m3,
        "mass_tons": measurement.mass_tons,
        "avg_height_m": measurement.avg_height_m,
        "cross_section_m2": measurement.cross_section_m2,
        "is_empty": measurement.is_empty,
        "empty_confidence": measurement.empty_confidence
    }


@router.get("/angle")
async def get_lidar_angle():
    if not lidar_client.is_connected:
        if not lidar_client.connect():
            raise HTTPException(status_code=503, detail="Лидар не подключен")
    
    angle_info = lidar_client.get_current_angle_range()
    
    if not angle_info:
        return {"status": "error", "message": "Не удалось получить информацию об угле"}
    
    return {
        "status": "ok",
        "current": angle_info,
        "target": {
            "start_angle_deg": -35.0,
            "stop_angle_deg": 35.0,
            "total_angle_deg": 70.0
        }
    }

@router.get("/profiles")
async def get_all_profiles():
    """Получить все профили техники"""
    return {
        "profiles": vehicle_profiles.get_all_profiles(),
        "count": len(vehicle_profiles.profiles)
    }

@router.get("/profiles/types")
async def get_profile_types():
    """Получить типы техники и количество профилей"""
    types = {}
    for name, profile in vehicle_profiles.profiles.items():
        types[profile.vehicle_type] = types.get(profile.vehicle_type, 0) + 1
    
    return {"types": types}

@router.post("/profiles/add")
async def add_profile(
    name: str,
    vehicle_type: str,
    length_m: float,
    width_m: float,
    height_m: float,
    empty_height_mm: float = 0,
    points_min: int = 10,
    points_max: int = 500,
    spread_min: int = 50,
    spread_max: int = 3000,
    brand: Optional[str] = None,
    model: Optional[str] = None
):
    """Добавить новый профиль техники"""
    profile = VehicleProfile(
        name=name,
        vehicle_type=vehicle_type,
        brand=brand,
        model=model,
        length_m=length_m,
        width_m=width_m,
        height_m=height_m,
        empty_height_mm=empty_height_mm,
        points_range=(points_min, points_max),
        spread_range=(spread_min, spread_max)
    )
    
    vehicle_profiles.add_profile(profile)
    
    return {
        "status": "success",
        "message": f"Профиль '{name}' добавлен",
        "profile": profile.to_dict()
    }