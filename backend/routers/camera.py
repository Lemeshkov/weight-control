# backend/routers/camera.py
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse
import asyncio
from datetime import datetime
import logging
from services.camera_client import CameraClient
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/camera", tags=["camera"])


camera_client = CameraClient(
    camera_type=settings.CAMERA_TYPE,
    ip=settings.CAMERA_IP,
    port=settings.CAMERA_PORT,
    username=settings.CAMERA_USERNAME,
    password=settings.CAMERA_PASSWORD,
    rtsp_path=settings.CAMERA_RTSP_PATH,
)

@router.on_event("startup")
async def startup_camera():
    try:
        if await asyncio.to_thread(camera_client.connect):
            logger.info(" Камера подключена")
        else:
            logger.warning(" Камера не подключена")
    except Exception as e:
        logger.error(f" Ошибка: {e}")

@router.on_event("shutdown")
async def shutdown_camera():
    await asyncio.to_thread(camera_client.disconnect)

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

@router.get("/stream")
async def stream_camera():
    """Непрерывный MJPEG-поток с автоматическим ожиданием переподключения."""
    async def frames():
        while True:
            frame = camera_client.get_frame()
            if frame:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Cache-Control: no-cache\r\n\r\n"
                    + frame["data"]
                    + b"\r\n"
                )
            await asyncio.sleep(0.2)

    return StreamingResponse(
        frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/status")
async def get_camera_status():
    """Статус камеры"""
    return {
        "connected": camera_client.is_connected,
        "type": camera_client.camera_type,
        "ip": camera_client.ip,
        "frame_timestamp": camera_client.frame_timestamp.isoformat() if camera_client.frame_timestamp else None,
        "errors": camera_client._error_count
    }
