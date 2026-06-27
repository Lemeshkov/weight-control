

# backend/routers/lidar.py

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
from services.object_detector import ObjectDetector

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
            # configure_lidar_angle()чтоб не сбрасывался при старте 
        else:
            logger.warning("⚠️ Лидар не подключен")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")


def configure_lidar_angle():
    try:
        if not lidar_client.sock or not lidar_client.is_connected:
            return False

        # ═══════════════════════════════════════════════════════════
        # ⭐ ДЛЯ HEX-ФОРМАТА ИСПОЛЬЗУЕМ ДРУГИЕ КОМАНДЫ
        # ═══════════════════════════════════════════════════════════
        # Устанавливаем угол 70° (-35°…+35°)
        # -35° = -3500 = FFFF3CB0 (в HEX)
        # +35° = 3500 = 0DAC (в HEX)
        # 70° = 7000 = 1B58 (в HEX)

        commands = [
            "sWN LMPoutputRange 1 5000 FFFF3CB0 0DAC",   # ← -35°…+35°
            "sWN LMPoutputRange 1 +5000 FFFF3CB0 +0DAC",
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
    """
    Получить данные сканирования с детекцией объекта
    """
    if not lidar_client.is_connected:
        if not lidar_client.connect():
            raise HTTPException(status_code=503, detail="Лидар не подключен")
    
    scan_data = lidar_client.get_scan_data()
    if not scan_data:
        raise HTTPException(status_code=500, detail="Не удалось получить данные")
    
    # ═══════════════════════════════════════════════════════════
    # ШАГ 1: Фильтрация через parse_scan_data
    # ═══════════════════════════════════════════════════════════
    parsed = lidar_client.parse_scan_data(
        scan_data, 
        filter_angle=True, 
        separate_object=True,
        mode="auto"
    )
    
    object_points = parsed.get("distances_mm", [])
    points_count = len(object_points)
    
    is_empty = parsed.get("is_empty", True)
    empty_confidence = parsed.get("empty_confidence", 0)
    empty_reason = parsed.get("empty_reason", "")
    object_type = parsed.get("object_type", "unknown")
    object_height_mm = parsed.get("object_height_mm", 0)
    floor_level_mm = parsed.get("floor_level_mm", 0)
    object_detected = parsed.get("object_detected", False)
    
    # ═══════════════════════════════════════════════════════════
    # ШАГ 2: Статус для фронтенда
    # ═══════════════════════════════════════════════════════════
    if points_count == 0:
        object_status = "no_object"
        status_text = "📭 Объект отсутствует"
    elif is_empty:
        object_status = "empty"
        status_text = "📦 Коробка/кузов ПУСТОЙ"
    else:
        object_status = "filled"
        status_text = "📦✅ Коробка/кузов ЗАПОЛНЕН"
    
    # ═══════════════════════════════════════════════════════════
    # ШАГ 3: Определяем тип через ObjectDetector
    # ═══════════════════════════════════════════════════════════
    box_info = {
        "box_type": "unknown",
        "box_label": "?",
        "box_name": "Неизвестная",
        "size_mm": {"width": 0, "depth": 0, "height": 0},
        "size_cm": {"width": 0, "depth": 0, "height": 0},
        "detected": False,
        "confidence": 0,
        "profile_name": None
    }
    
    profile_obj = None
    profile_confidence = 0
    profile_dict = None
    
    if points_count > 0:
        try:
            detection_result = ObjectDetector.process_scan(
                object_points, 
                {"floor_level": floor_level_mm}
            )
            
            profile_obj = detection_result.get("profile")
            profile_confidence = detection_result.get("profile_confidence", 0)
            box_info = detection_result.get("box_info", box_info)
            
            if profile_obj and hasattr(profile_obj, 'to_dict'):
                profile_dict = profile_obj.to_dict()
                
                if box_info.get("detected") and box_info.get("vehicle_type") == "box":
                    box_label = box_info.get("box_label", "?")
                    size_cm = box_info.get("size_cm", {})
                    size_str = f"{size_cm.get('width', 0)}×{size_cm.get('depth', 0)}×{size_cm.get('height', 0)}"
                    
                    if is_empty:
                        status_text = f"📦 Коробка {box_label} ({size_str}см) ПУСТАЯ"
                    else:
                        status_text = f"📦 Коробка {box_label} ({size_str}см) ЗАПОЛНЕНА"
                elif box_info.get("detected") and box_info.get("vehicle_type") == "truck":
                    if is_empty:
                        status_text = f"🚛 {box_info.get('profile_name', 'Грузовик')} ПУСТОЙ"
                    else:
                        status_text = f"🚛 {box_info.get('profile_name', 'Грузовик')} ЗАПОЛНЕН"
            
            # ⭐ ЛОГИРОВАНИЕ (исправлено)
            if profile_obj and hasattr(profile_obj, 'name'):
                logger.info(f"🔍 ObjectDetector: box_info={box_info.get('box_label', '?')}, profile={profile_obj.name}")
            elif profile_obj and isinstance(profile_obj, dict):
                logger.info(f"🔍 ObjectDetector: box_info={box_info.get('box_label', '?')}, profile={profile_obj.get('name', 'Unknown')}")
            else:
                logger.info(f"🔍 ObjectDetector: box_info={box_info.get('box_label', '?')}, profile=None")
                
        except Exception as e:
            logger.warning(f"⚠️ Ошибка в ObjectDetector: {e}")
    
    # ═══════════════════════════════════════════════════════════
    # ШАГ 4: Ответ
    # ═══════════════════════════════════════════════════════════
    return {
        "timestamp": datetime.now().isoformat(),
        "points_count": points_count,
        "distances_mm": object_points,
        "distances_m": [d / 1000 for d in object_points] if object_points else [],
        
        "statistics": {
            "min_mm": parsed.get("min_distance_mm", 0),
            "max_mm": parsed.get("max_distance_mm", 0),
            "avg_mm": parsed.get("avg_distance_mm", 0),
            "min_m": parsed.get("min_distance_m", 0),
            "max_m": parsed.get("max_distance_m", 0),
            "avg_m": parsed.get("avg_distance_m", 0)
        },
        
        "object_status": object_status,
        "status_text": status_text,
        "object_detected": object_detected,
        "is_empty": is_empty,
        "empty_confidence": empty_confidence,
        "empty_reason": empty_reason,
        "object_type": object_type,
        "object_height_mm": object_height_mm,
        "floor_level_mm": floor_level_mm,
        "spread_mm": parsed.get("spread_mm", 0),
        
        "box_info": box_info,
        "profile": profile_dict,
        "profile_confidence": profile_confidence,
        "reason": empty_reason
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
    
    distances_mm = lidar_client.parse_raw_data(scan_data)
    
    if not distances_mm:
        raise HTTPException(status_code=400, detail="Нет данных в скане")
    
    angle_filtered = lidar_client.filter_to_70_degrees(distances_mm)
    valid_distances = lidar_client.filter_valid_distances(angle_filtered)
    
    detection_result = ObjectDetector.process_scan(valid_distances)
    
    is_empty = detection_result.get("is_empty", True)
    empty_confidence = detection_result.get("confidence", 0)
    object_type = detection_result.get("object_type", "unknown")
    object_height_mm = detection_result.get("object_height_mm", 0)
    box_info = detection_result.get("box_info", {})
    
    if not is_empty and valid_distances:
        floor_level = detection_result.get("floor_level_mm", max(valid_distances))
        roadLevel = floor_level / 1000
        
        heights = []
        for d in valid_distances:
            distM = d / 1000
            if distM < roadLevel - 0.03:
                heights.append(roadLevel - distM)
            else:
                heights.append(0)
        
        validHeights = [h for h in heights if h > 0.01]
        
        if validHeights:
            avgHeight = sum(validHeights) / len(validHeights)
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
        points_count=len(valid_distances),
        distances_mm=valid_distances,
        distances_m=[d/1000 for d in valid_distances],
        volume_m3=round(volume_m3, 3),
        mass_tons=round(mass_tons, 2),
        avg_height_m=round(avgHeight, 2),
        cross_section_m2=round(cross_section, 3),
        truck_length_m=request.truck_length_m,
        truck_width_m=request.truck_width_m,
        coal_density_kg_m3=request.coal_density_kg_m3,
        is_empty=is_empty,
        empty_confidence=empty_confidence,
        empty_reason=detection_result.get("reason", "")
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
        "empty_reason": detection_result.get("reason", ""),
        "object_type": object_type,
        "box_info": box_info,
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
    model: Optional[str] = None,
    box_type: Optional[str] = None
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
        spread_range=(spread_min, spread_max),
        box_type=box_type if box_type else "unknown"
    )
    
    vehicle_profiles.add_profile(profile)
    
    return {
        "status": "success",
        "message": f"Профиль '{name}' добавлен",
        "profile": profile.to_dict()
    }


@router.get("/debug-points")
async def debug_points():
    """Диагностика количества точек до и после фильтрации"""
    if not lidar_client.is_connected:
        if not lidar_client.connect():
            raise HTTPException(status_code=503, detail="Лидар не подключен")
    
    scan_data = lidar_client.get_scan_data()
    if not scan_data:
        raise HTTPException(status_code=500, detail="Не удалось получить данные")
    
    distances_mm = lidar_client.parse_raw_data(scan_data)
    
    if not distances_mm:
        return {"error": "Нет данных"}
    
    angle_filtered = lidar_client.filter_to_70_degrees(distances_mm)
    valid_distances = lidar_client.filter_valid_distances(angle_filtered)
    
    detection_result = ObjectDetector.process_scan(valid_distances)
    
    return {
        "raw_points_count": len(distances_mm),
        "angle_filtered_count": len(angle_filtered),
        "valid_points_count": len(valid_distances),
        "object_points_count": detection_result.get("points_count", 0),
        "is_empty": detection_result.get("is_empty", True),
        "object_type": detection_result.get("object_type", "unknown"),
        "object_height_mm": detection_result.get("object_height_mm", 0),
        "box_info": detection_result.get("box_info", {}),
        "reason": detection_result.get("reason", ""),
        "sample_distances": valid_distances[:20]
    }


@router.get("/debug-bounds")
async def debug_object_bounds():
    """
    Диагностика границ объекта по профилю
    """
    if not lidar_client.is_connected:
        if not lidar_client.connect():
            raise HTTPException(status_code=503, detail="Лидар не подключен")
    
    scan_data = lidar_client.get_scan_data()
    if not scan_data:
        raise HTTPException(status_code=500, detail="Не удалось получить данные")
    
    distances_mm = lidar_client.parse_raw_data(scan_data)
    
    if not distances_mm:
        return {"error": "Нет данных"}
    
    angle_filtered = lidar_client.filter_to_70_degrees(distances_mm)
    valid_distances = lidar_client.filter_valid_distances(angle_filtered)
    
    detection_result = ObjectDetector.process_scan(valid_distances)
    
    floor_level = detection_result.get("floor_level_mm", 0)
    profile = detection_result.get("profile")
    points = detection_result.get("points", [])
    
    if profile:
        bounds = profile.get_bounds(points, floor_level)
        filtered = profile.filter_points_inside(points, floor_level)
        bounds["points"]["inside"] = len(filtered)
        
        return {
            "profile": profile.name,
            "profile_confidence": detection_result.get("profile_confidence", 0),
            "bounds": bounds,
            "points_count": len(points),
            "points_inside": len(filtered),
            "points_sample": points[:20]
        }
    else:
        return {
            "error": "Профиль не найден",
            "points_count": len(points)
        }


@router.get("/debug/raw-data")
async def debug_raw_data():
    """
    Получить СЫРЫЕ данные с лидара без фильтрации
    """
    if not lidar_client.is_connected:
        if not lidar_client.connect():
            raise HTTPException(status_code=503, detail="Лидар не подключен")

    scan_data = lidar_client.get_scan_data()
    if not scan_data:
        raise HTTPException(status_code=500, detail="Не удалось получить данные")

    # Парсим сырые данные
    raw_distances = lidar_client.parse_raw_data(scan_data)

    # Применяем фильтр угла
    angle_filtered = lidar_client.filter_angle(raw_distances, 70)

    # Фильтруем шум
    noise_filtered = [d for d in angle_filtered if 1000 <= d <= 3000]

    # Ищем кластер объекта
    object_points = lidar_client._find_object_cluster(noise_filtered)

    return {
        "raw": {
            "total": len(raw_distances),
            "sample": raw_distances[:50],
            "min": min(raw_distances) if raw_distances else 0,
            "max": max(raw_distances) if raw_distances else 0,
            "histogram": dict(sorted(
                {int(d/50)*50: len([x for x in raw_distances if int(x/50)*50 == int(d/50)*50])
                    for d in raw_distances[:200]}.items()
            ))
        },
        "after_angle_filter": {
            "total": len(angle_filtered),
            "sample": angle_filtered[:30]
        },
        "after_noise_filter": {
            "total": len(noise_filtered),
            "sample": noise_filtered[:30]
        },
        "object": {
            "detected": len(object_points) >= 15,
            "points": len(object_points),
            "sample": object_points[:30],
            "min": min(object_points) if object_points else 0,
            "max": max(object_points) if object_points else 0,
            "floor_level": lidar_client.FLOOR_LEVEL,
            "height_mm": lidar_client.FLOOR_LEVEL - min(object_points) if object_points else 0
        },
        "settings": {
            "MIN_VALID_DISTANCE": lidar_client.MIN_VALID_DISTANCE,
            "FLOOR_LEVEL": lidar_client.FLOOR_LEVEL,
            "FLOOR_THRESHOLD": lidar_client.FLOOR_THRESHOLD,
            "MIN_OBJECT_POINTS": lidar_client.MIN_OBJECT_POINTS
        }
    }
    

@router.get("/debug/frontend-data")
async def get_frontend_format():
    """
    Получить данные в формате, который ожидает фронтенд
    """
    if not lidar_client.is_connected:
        if not lidar_client.connect():
            raise HTTPException(status_code=503, detail="Лидар не подключен")

    scan_data = lidar_client.get_scan_data()
    if not scan_data:
        raise HTTPException(status_code=500, detail="Не удалось получить данные")

    # Парсим как обычно
    parsed = lidar_client.parse_scan_data(
        scan_data,
        filter_angle=True,
        separate_object=True,
        mode="auto"
    )

    # Формируем данные для диаграммы
    distances = parsed.get("distances_mm", [])

    # Создаем точки для графика (x - индекс, y - расстояние)
    chart_data = []
    for i, d in enumerate(distances):
        chart_data.append({
            "index": i,
            "distance": d,
            "distance_m": round(d / 1000, 2)
        })

    return {
        "chart_data": chart_data,
        "points_count": len(distances),
        "floor_level": parsed.get("floor_level_mm", 0),
        "object_height": parsed.get("object_height_mm", 0),
        "is_empty": parsed.get("is_empty", True),
        "object_type": parsed.get("object_type", "unknown"),
        "raw_distances": distances[:100],  # первые 100 точек для отладки
        "statistics": {
            "min": min(distances) if distances else 0,
            "max": max(distances) if distances else 0,
            "avg": sum(distances) / len(distances) if distances else 0,
            "count": len(distances)
        }
    }