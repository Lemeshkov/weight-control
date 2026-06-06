# backend/routers/camera.py
from fastapi import APIRouter, HTTPException, Response
from datetime import datetime
import logging
from services.camera_client import CameraClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/camera", tags=["camera"])

# Настройка для камеры Hikvision
camera_client = CameraClient(
    camera_type="ip",
    ip="192.168.1.64",        
    port=554,                 
    username="admin",         
    password="Hikvision",      
    rtsp_path="/Streaming/Channels/101"  
)

@router.on_event("startup")
async def startup_camera():
    try:
        if camera_client.connect():
            logger.info("✅ Камера подключена")
        else:
            logger.warning("⚠️ Камера не подключена")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

@router.on_event("shutdown")
async def shutdown_camera():
    camera_client.disconnect()

@router.get("/frame")
async def get_camera_frame():
    """Получить текущий кадр с камеры"""
    frame = camera_client.get_frame()
    if not frame:
        raise HTTPException(status_code=503, detail="Камера не подключена или нет кадров")
    
    return Response(
        content=frame["data"],
        media_type="image/jpeg",
        headers={
            "X-Timestamp": frame["timestamp"],
            "X-Width": str(frame["width"]),
            "X-Height": str(frame["height"])
        }
    )

@router.get("/status")
async def get_camera_status():
    """Статус камеры"""
    return {
        "connected": camera_client.is_connected,
        "type": camera_client.camera_type,
        "ip": camera_client.ip
    }