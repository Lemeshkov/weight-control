# backend/routers/lidar.py
from fastapi import APIRouter, HTTPException
from datetime import datetime
import logging
from services.lidar_client import LidarClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/lidar", tags=["lidar"])

lidar_client = LidarClient(host="192.168.1.101", port=2111)

@router.on_event("startup")
async def startup_lidar():
    try:
        if lidar_client.connect():
            logger.info("✅ Лидар подключен")
        else:
            logger.warning("⚠️ Лидар не подключен")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

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
        "host": "192.168.0.1",
        "port": 2111
    }

# # backend/routers/lidar.py
# from fastapi import APIRouter, HTTPException
# from datetime import datetime
# from services.lidar_client import LidarClient

# router = APIRouter(prefix="/api/lidar", tags=["lidar"])

# # Создаем экземпляр клиента здесь, а не импортируем из main
# lidar_client = LidarClient(host="192.168.0.1", port=2111)

# @router.on_event("startup")
# async def startup_lidar():
#     """Подключаемся к лидару при старте роутера"""
#     if not lidar_client.is_connected:
#         lidar_client.connect()

# @router.on_event("shutdown")
# async def shutdown_lidar():
#     """Отключаемся при остановке"""
#     if lidar_client.is_connected:
#         lidar_client.disconnect()

# @router.get("/scan")
# async def get_lidar_scan():
#     """Получить текущие данные сканирования с лидара"""
#     if not lidar_client or not lidar_client.is_connected:
#         raise HTTPException(status_code=503, detail="Лидар не подключен")
    
#     scan_data = lidar_client.get_scan_data()
#     if not scan_data:
#         raise HTTPException(status_code=500, detail="Не удалось получить данные с лидара")
    
#     return {
#         "timestamp": datetime.now().isoformat(),
#         "data": scan_data
#     }

# @router.get("/status")
# async def get_lidar_status():
#     """Проверить статус подключения к лидару"""
#     return {
#         "is_connected": lidar_client.is_connected if lidar_client else False,
#         "host": "192.168.0.1",
#         "port": 2111
#     }

# @router.post("/connect")
# async def connect_lidar():
#     """Принудительное подключение к лидару"""
#     if lidar_client.is_connected:
#         return {"status": "already_connected"}
    
#     if lidar_client.connect():
#         return {"status": "connected"}
#     else:
#         raise HTTPException(status_code=500, detail="Не удалось подключиться к лидару")

# @router.post("/disconnect")
# async def disconnect_lidar():
#     """Принудительное отключение от лидара"""
#     lidar_client.disconnect()
#     return {"status": "disconnected"}