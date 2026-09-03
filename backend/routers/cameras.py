import asyncio
import logging
import time
from fastapi import APIRouter,HTTPException
from fastapi.responses import StreamingResponse
from routers.camera import camera_client as top_camera
from services.side_camera_service import side_camera_service

router=APIRouter(prefix='/api/cameras',tags=['cameras'])
def top_status():
 frame=top_camera.get_frame();age=None
 if top_camera._last_frame_monotonic_ns:age=max(0,(time.monotonic_ns()-top_camera._last_frame_monotonic_ns)/1e6)
 return {'enabled':True,'connected':top_camera.is_connected,'stale':age is None or age>1000,'measured_fps':top_camera.acquisition_fps,'frame_age_ms':round(age,3) if age is not None else None,'frame_counter':frame.get('sequence_number') if frame else top_camera._frame_sequence,'resolution':f"{frame['width']}x{frame['height']}" if frame else None,'reconnect_count':top_camera.rtsp_reconnect_count,'frame_gap_count':None,'last_frame_gap_ms':None,'last_error':None if top_camera.is_connected else 'NOT_CONNECTED'}
@router.on_event('startup')
async def startup_side_camera():
 status=side_camera_service.status();logger=logging.getLogger(__name__);logger.info('SIDE_CAMERA_ENABLED=%s SIDE_CAMERA_CONFIGURED=%s SIDE_CAMERA_ENDPOINT=%s TARGET_FPS=%s',status['enabled'],status['configured'],status['redacted_endpoint'],status['target_fps']);await asyncio.to_thread(side_camera_service.start)
@router.on_event('shutdown')
async def shutdown_side_camera():await asyncio.to_thread(side_camera_service.stop)
@router.get('/status')
async def cameras_status():return {'top':top_status(),'side':side_camera_service.status()}
async def side_frames(poll_interval=.05):
 last=None
 while True:
  client=side_camera_service.client;frame=client.get_frame() if client else None
  if frame and frame['sequence_number']!=last:
   last=frame['sequence_number'];yield b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: '+str(frame['size']).encode()+b'\r\nCache-Control: no-store\r\n\r\n'+frame['data']+b'\r\n'
  await asyncio.sleep(poll_interval)
@router.get('/side/stream')
async def side_stream():
 if not side_camera_service.enabled:raise HTTPException(503,'SIDE_CAMERA_DISABLED')
 return StreamingResponse(side_frames(),media_type='multipart/x-mixed-replace; boundary=frame',headers={'Cache-Control':'no-store, no-cache, must-revalidate','X-Accel-Buffering':'no'})
