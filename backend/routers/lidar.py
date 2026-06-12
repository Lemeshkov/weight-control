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
    """Получить данные сканирования (без сохранения)"""
    if not lidar_client.is_connected:
        if not lidar_client.connect():
            raise HTTPException(status_code=503, detail="Лидар не подключен")
    
    scan_data = lidar_client.get_scan_data()
    if not scan_data:
        raise HTTPException(status_code=500, detail="Не удалось получить данные")
    
    parsed = lidar_client.parse_scan_data(scan_data, filter_angle=True, separate_object=False)
    
    return {
        "timestamp": datetime.now().isoformat(),
        "points_count": parsed.get("points_count", 0),
        "distances_mm": parsed.get("distances_mm", []),
        "distances_m": parsed.get("distances_m", []),
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
    
    parsed = lidar_client.parse_scan_data(scan_data, filter_angle=True, separate_object=False)
    distances_mm = parsed.get("distances_mm", [])
    
    if not distances_mm:
        raise HTTPException(status_code=400, detail="Нет данных в скане")
    
    # Расчёт объёма
    roadLevel = max(distances_mm) / 1000
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
        volume_m3 = request.truck_length_m * request.truck_width_m * avgHeight
        mass_tons = (volume_m3 * request.coal_density_kg_m3) / 1000
        cross_section = avgHeight * request.truck_width_m
        is_empty = len(distances_mm) < 15
    else:
        volume_m3 = 0
        mass_tons = 0
        cross_section = 0
        avgHeight = 0
        is_empty = True
    
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
        empty_confidence=95 if is_empty else 0
    )
    
    db.add(measurement)
    db.commit()
    db.refresh(measurement)
    
    logger.info(f"✅ Измерение сохранено: ID={measurement.id}, объём={volume_m3:.3f}м³")
    
    return {
        "id": measurement.id,
        "timestamp": measurement.timestamp.isoformat(),
        "points_count": measurement.points_count,
        "volume_m3": measurement.volume_m3,
        "mass_tons": measurement.mass_tons,
        "avg_height_m": measurement.avg_height_m,
        "cross_section_m2": measurement.cross_section_m2,
        "is_empty": measurement.is_empty,
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
            "is_empty": m.is_empty
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
        "is_empty": measurement.is_empty
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

# # backend/routers/lidar.py (упрощённая версия без БД)
# from fastapi import APIRouter, HTTPException
# from datetime import datetime
# import logging
# from services.lidar_client import LidarClient
# import time

# logger = logging.getLogger(__name__)
# router = APIRouter(prefix="/api/lidar", tags=["lidar"])

# lidar_client = LidarClient(host="192.168.1.101", port=2111)


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
#     """Получить данные сканирования"""
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


# Временно отключаем эндпоинты с БД
# @router.post("/measure")
# async def measure_and_save(...):
#     ...

# @router.get("/measurements")
# async def get_measurements(...):
#     ...

# # backend/routers/lidar.py
# from fastapi import APIRouter, HTTPException, Depends
# from datetime import datetime
# import logging
# from services.lidar_client import LidarClient
# from sqlalchemy.orm import Session
# from database import get_db
# import time
# from models import LidarMeasurement, Trip
# from pydantic import BaseModel
# from typing import Optional

# logger = logging.getLogger(__name__)
# router = APIRouter(prefix="/api/lidar", tags=["lidar"])

# lidar_client = LidarClient(host="192.168.1.101", port=2111)


# class MeasurementResponse(BaseModel):
#     id: int
#     timestamp: str
#     points_count: int
#     volume_m3: float
#     mass_tons: float
#     avg_height_m: float
#     cross_section_m2: float
#     is_empty: bool
#     truck_length_m: float
#     truck_width_m: float


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
#     """Настройка угла сканирования"""
#     try:
#         if not lidar_client.sock or not lidar_client.is_connected:
#             logger.error("Нет соединения с лидаром")
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


# @router.post("/measure")
# async def measure_and_save(
#     request: SingleScanRequest,
#     db: Session = Depends(get_db)
# ):
#     """
#     Выполнить ОДНО сканирование, рассчитать объём и сохранить в БД
#     """
#     if not lidar_client.is_connected:
#         if not lidar_client.connect():
#             raise HTTPException(status_code=503, detail="Лидар не подключен")
    
#     # 1. Получаем данные
#     scan_data = lidar_client.get_scan_data()
#     if not scan_data:
#         raise HTTPException(status_code=500, detail="Не удалось получить данные")
    
#     # 2. Парсим (без отделения объекта, чтобы получить все точки)
#     parsed = lidar_client.parse_scan_data(scan_data, filter_angle=True, separate_object=False)
    
#     distances_mm = parsed.get("distances_mm", [])
    
#     if not distances_mm:
#         raise HTTPException(status_code=400, detail="Нет данных в скане")
    
#     # 3. Рассчитываем объём
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
    
#     # 4. Сохраняем в БД
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
    
#     logger.info(f"✅ Измерение сохранено: ID={measurement.id}, объём={volume_m3:.3f}м³, пусто={is_empty}")
    
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
#     """Получить историю измерений"""
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
#             "is_empty": m.is_empty,
#             "truck_length_m": m.truck_length_m,
#             "truck_width_m": m.truck_width_m
#         }
#         for m in measurements
#     ]


# @router.get("/measurements/{measurement_id}")
# async def get_measurement(measurement_id: int, db: Session = Depends(get_db)):
#     """Получить конкретное измерение с полными данными"""
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
#         "is_empty": measurement.is_empty,
#         "truck_length_m": measurement.truck_length_m,
#         "truck_width_m": measurement.truck_width_m
#     }


# @router.get("/scan")
# async def get_lidar_scan():
#     """
#     Получить данные сканирования (без сохранения)
#     Только для предпросмотра
#     """
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
#         "connected": lidar_client.is_connected if lidar_client else False,
#         "host": "192.168.1.101",
#         "port": 2111
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


# @router.post("/configure-angle")
# async def configure_angle_endpoint():
#     if not lidar_client.is_connected:
#         if not lidar_client.connect():
#             raise HTTPException(status_code=503, detail="Не удалось подключиться к лидару")
    
#     success = configure_lidar_angle()
#     if success:
#         return {
#             "status": "configured",
#             "message": "Угол сканирования установлен: -35°...+35° (70°)",
#             "start_angle_deg": -35,
#             "stop_angle_deg": 35
#         }
#     else:
#         raise HTTPException(status_code=500, detail="Не удалось настроить угол сканирования")

# # backend/routers/lidar.py
# from fastapi import APIRouter, HTTPException
# from datetime import datetime
# import logging
# from services.lidar_client import LidarClient
# import time 

# logger = logging.getLogger(__name__)
# router = APIRouter(prefix="/api/lidar", tags=["lidar"])

# # Создаем клиент с правильным IP
# lidar_client = LidarClient(host="192.168.1.101", port=2111)

# @router.on_event("startup")
# async def startup_lidar():
#     try:
#         if lidar_client.connect():
#             logger.info("✅ Лидар подключен")
#             # После подключения настраиваем угол сканирования
#             configure_lidar_angle()  # ← УБРАТЬ await (это не async функция)
#         else:
#             logger.warning("⚠️ Лидар не подключен")
#     except Exception as e:
#         logger.error(f"❌ Ошибка: {e}")

# def configure_lidar_angle():
#     """
#     Настройка угла сканирования лидара.
#     Устанавливает выходной диапазон -35°...+35° (70° симметрично)
#     """
#     try:
#         if not lidar_client.sock or not lidar_client.is_connected:
#             logger.error("Нет соединения с лидаром для настройки угла")
#             return False
        
#         # ВАЖНО: используем десятичные значения, а не HEX
#         # Разрешение: 5000 = 0.5°
#         # Начальный угол: -3500 = -35°
#         # Конечный угол: 3500 = +35°
        
#         # Формат команды для LMS511:
#         # sWN LMPoutputRange [status] [resolution] [start_angle] [stop_angle]
        
#         # Пробуем разные варианты
#         commands = [
#             "sWN LMPoutputRange 1 5000 -3500 3500",
#             "sWN LMPoutputRange 1 +5000 -3500 +3500",
#         ]
        
#         for cmd in commands:
#             logger.info(f"Пробуем: {cmd}")
#             result = lidar_client._send_raw(cmd)
#             logger.info(f"Результат: {result}")
#             time.sleep(0.2)
        
#         # Применяем настройки
#         lidar_client._send_raw("sMN Logout")
#         time.sleep(0.2)
#         lidar_client._send_raw("sMN SetAccessMode 3 F4724744")
#         time.sleep(0.2)
#         lidar_client._send_raw("sMN Run")
#         time.sleep(0.2)
        
#         # Проверяем результат
#         check = lidar_client._send_raw("sRN LMPoutputRange")
#         logger.info(f"Проверка угла: {check}")
        
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
#     """Получить данные сканирования"""
#     if not lidar_client:
#         raise HTTPException(status_code=503, detail="Лидар не инициализирован")
    
#     if not lidar_client.is_connected:
#         if not lidar_client.connect():
#             raise HTTPException(status_code=503, detail="Не удалось подключиться к лидару")
    
#     scan_data = lidar_client.get_scan_data()
#     if not scan_data:
#         raise HTTPException(status_code=500, detail="Не удалось получить данные")
    
#     parsed = lidar_client.parse_scan_data(scan_data, filter_angle=True, separate_object=True)
    
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
#         "connected": lidar_client.is_connected if lidar_client else False,
#         "host": "192.168.1.101",
#         "port": 2111
#     }

# @router.get("/angle")
# async def get_lidar_angle():
#     """
#     Получить текущий угол сканирования
#     """
#     if not lidar_client.is_connected:
#         if not lidar_client.connect():
#             raise HTTPException(status_code=503, detail="Лидар не подключен")
    
#     angle_info = lidar_client.get_current_angle_range()
    
#     if not angle_info:
#         return {
#             "status": "error",
#             "message": "Не удалось получить информацию об угле"
#         }
    
#     return {
#         "status": "ok",
#         "current": angle_info,
#         "target": {
#             "start_angle_deg": -35.0,
#             "stop_angle_deg": 35.0,
#             "total_angle_deg": 70.0
#         }
#     }

# @router.post("/configure-angle")
# async def configure_angle_endpoint():
#     """
#     Эндпоинт для ручной настройки угла сканирования
#     """
#     if not lidar_client.is_connected:
#         if not lidar_client.connect():
#             raise HTTPException(status_code=503, detail="Не удалось подключиться к лидару")
    
#     success = configure_lidar_angle()
#     if success:
#         return {
#             "status": "configured",
#             "message": "Угол сканирования установлен: -35°...+35° (70°)",
#             "start_angle_deg": -35,
#             "stop_angle_deg": 35
#         }
#     else:
#         raise HTTPException(status_code=500, detail="Не удалось настроить угол сканирования")

# @router.get("/empty-status")
# async def check_empty_status():
#     """
#     Проверить, пустой ли кузов
#     """
#     if not lidar_client.is_connected:
#         raise HTTPException(status_code=503, detail="Лидар не подключен")
    
#     scan_data = lidar_client.get_scan_data()
#     if not scan_data:
#         raise HTTPException(status_code=500, detail="Нет данных")
    
#     parsed = lidar_client.parse_scan_data(scan_data, filter_angle=True, separate_object=True)
#     empty_status = lidar_client.check_if_empty(parsed)
    
#     return {
#         "timestamp": datetime.now().isoformat(),
#         "is_empty": empty_status["is_empty"],
#         "confidence": empty_status["confidence"],
#         "reason": empty_status["reason"],
#         "points_count": empty_status["points_count"]
#     }