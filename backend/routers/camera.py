# backend/routers/camera.py
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
import asyncio
from datetime import datetime
import logging
import time
from services.camera_client import CameraClient
from config import settings
from services.camera_lidar_diagnostic_recorder import diagnostic_recorder

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/camera", tags=["camera"])
active_stream_clients = 0


class DiagnosticMarker(BaseModel):
    label: str


camera_client = CameraClient(
    camera_type=settings.CAMERA_TYPE,
    ip=settings.CAMERA_IP,
    port=settings.CAMERA_PORT,
    username=settings.CAMERA_USERNAME,
    password=settings.CAMERA_PASSWORD,
    rtsp_path=settings.CAMERA_RTSP_PATH,
    capture_mode=settings.CAMERA_CAPTURE_MODE,
    rtsp_fallback_to_snapshot=settings.CAMERA_RTSP_FALLBACK_TO_SNAPSHOT,
    rtsp_reconnect_seconds=settings.CAMERA_RTSP_RECONNECT_SECONDS,
)


async def camera_mjpeg_frames(client: CameraClient, poll_interval: float = 0.05):
    """Yield each newly published CameraClient sequence once per consumer."""
    global active_stream_clients
    active_stream_clients += 1
    logger.info("Camera stream connected: active_clients=%s", active_stream_clients)
    no_frame_since = time.monotonic()
    last_sequence = None
    try:
        while True:
            frame = client.get_frame()
            if frame:
                no_frame_since = time.monotonic()
                sequence = frame.get("sequence_number")
                if sequence != last_sequence:
                    last_sequence = sequence
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: " + str(frame["size"]).encode("ascii") + b"\r\n"
                        b"Cache-Control: no-store, no-cache, must-revalidate\r\n\r\n"
                        + frame["data"]
                        + b"\r\n"
                    )
            elif time.monotonic() - no_frame_since >= 3:
                logger.warning("Camera stream closed: no frame available")
                return
            await asyncio.sleep(poll_interval)
    finally:
        active_stream_clients = max(0, active_stream_clients - 1)
        logger.info("Camera stream disconnected: active_clients=%s", active_stream_clients)

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
    started = time.perf_counter()
    frame = camera_client.get_frame()
    if not frame:
        raise HTTPException(status_code=503, detail="Камера не подключена или нет кадров")
    
    logger.info(
        "Camera frame served: bytes=%s duration_ms=%.1f",
        frame["size"],
        (time.perf_counter() - started) * 1000,
    )
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
    return StreamingResponse(
        camera_mjpeg_frames(camera_client),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/status")
async def get_camera_status():
    """Статус камеры"""
    return {
        "connected": camera_client.is_connected,
        "type": camera_client.camera_type,
        "ip": camera_client.ip,
        "frame_timestamp": camera_client.frame_timestamp.isoformat() if camera_client.frame_timestamp else None,
        "errors": camera_client._error_count,
        "capture_mode": camera_client.active_capture_mode,
        "acquisition_fps": camera_client.acquisition_fps,
        "last_read_latency_ms": camera_client.last_read_latency_ms,
        "rtsp_reconnect_count": camera_client.rtsp_reconnect_count,
        "rtsp_failed_reads": camera_client.rtsp_failed_reads,
        "active_stream_clients": active_stream_clients,
    }


@router.post("/debug/diagnostics/marker")
async def add_diagnostic_marker(marker: DiagnosticMarker):
    """Dev/research marker; unavailable unless opt-in recording is active."""
    label = marker.label.strip().upper()
    if not diagnostic_recorder.marker(label):
        raise HTTPException(status_code=409, detail="Diagnostic recording inactive or invalid marker")
    return {"recorded": True, "label": label}


@router.get("/debug/diagnostics/status")
async def get_diagnostic_status():
    """Controlled-test recorder status; does not affect camera/status contract."""
    return diagnostic_recorder.status()


@router.post("/debug/diagnostics/finish")
async def finish_diagnostic_recording():
    """Explicitly flush and finish an active controlled-test recording."""
    if not diagnostic_recorder.active:
        raise HTTPException(status_code=409, detail="Diagnostic recording inactive")
    finished = await asyncio.to_thread(diagnostic_recorder.finish)
    if not finished:
        raise HTTPException(status_code=409, detail="Diagnostic recording inactive")
    return {"finished": True, "diagnostic_active": False}
