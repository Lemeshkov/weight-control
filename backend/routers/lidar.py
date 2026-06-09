# backend/routers/lidar.py
from fastapi import APIRouter, HTTPException
from datetime import datetime
import logging
from services.lidar_client import LidarClient
import time 

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/lidar", tags=["lidar"])

# Создаем клиент с правильным IP
lidar_client = LidarClient(host="192.168.1.101", port=2111)

@router.on_event("startup")
async def startup_lidar():
    try:
        if lidar_client.connect():
            logger.info("✅ Лидар подключен")
            # После подключения настраиваем угол сканирования
            configure_lidar_angle()  # ← УБРАТЬ await (это не async функция)
        else:
            logger.warning("⚠️ Лидар не подключен")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

def configure_lidar_angle():
    """
    Настройка угла сканирования лидара.
    Устанавливает выходной диапазон -35°...+35° (70° симметрично)
    """
    try:
        if not lidar_client.sock or not lidar_client.is_connected:
            logger.error("Нет соединения с лидаром для настройки угла")
            return False
        
        # ВАЖНО: используем десятичные значения, а не HEX
        # Разрешение: 5000 = 0.5°
        # Начальный угол: -3500 = -35°
        # Конечный угол: 3500 = +35°
        
        # Формат команды для LMS511:
        # sWN LMPoutputRange [status] [resolution] [start_angle] [stop_angle]
        
        # Пробуем разные варианты
        commands = [
            "sWN LMPoutputRange 1 5000 -3500 3500",
            "sWN LMPoutputRange 1 +5000 -3500 +3500",
        ]
        
        for cmd in commands:
            logger.info(f"Пробуем: {cmd}")
            result = lidar_client._send_raw(cmd)
            logger.info(f"Результат: {result}")
            time.sleep(0.2)
        
        # Применяем настройки
        lidar_client._send_raw("sMN Logout")
        time.sleep(0.2)
        lidar_client._send_raw("sMN SetAccessMode 3 F4724744")
        time.sleep(0.2)
        lidar_client._send_raw("sMN Run")
        time.sleep(0.2)
        
        # Проверяем результат
        check = lidar_client._send_raw("sRN LMPoutputRange")
        logger.info(f"Проверка угла: {check}")
        
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
    """Получить данные сканирования"""
    if not lidar_client:
        raise HTTPException(status_code=503, detail="Лидар не инициализирован")
    
    if not lidar_client.is_connected:
        if not lidar_client.connect():
            raise HTTPException(status_code=503, detail="Не удалось подключиться к лидару")
    
    scan_data = lidar_client.get_scan_data()
    if not scan_data:
        raise HTTPException(status_code=500, detail="Не удалось получить данные")
    
    parsed = lidar_client.parse_scan_data(scan_data)
    
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
        "connected": lidar_client.is_connected if lidar_client else False,
        "host": "192.168.1.101",
        "port": 2111
    }

@router.get("/angle")
async def get_lidar_angle():
    """
    Получить текущий угол сканирования
    """
    if not lidar_client.is_connected:
        if not lidar_client.connect():
            raise HTTPException(status_code=503, detail="Лидар не подключен")
    
    angle_info = lidar_client.get_current_angle_range()
    
    if not angle_info:
        return {
            "status": "error",
            "message": "Не удалось получить информацию об угле"
        }
    
    return {
        "status": "ok",
        "current": angle_info,
        "target": {
            "start_angle_deg": -35.0,
            "stop_angle_deg": 35.0,
            "total_angle_deg": 70.0
        }
    }

@router.post("/configure-angle")
async def configure_angle_endpoint():
    """
    Эндпоинт для ручной настройки угла сканирования
    """
    if not lidar_client.is_connected:
        if not lidar_client.connect():
            raise HTTPException(status_code=503, detail="Не удалось подключиться к лидару")
    
    success = configure_lidar_angle()
    if success:
        return {
            "status": "configured",
            "message": "Угол сканирования установлен: -35°...+35° (70°)",
            "start_angle_deg": -35,
            "stop_angle_deg": 35
        }
    else:
        raise HTTPException(status_code=500, detail="Не удалось настроить угол сканирования")

