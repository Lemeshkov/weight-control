from fastapi import APIRouter,HTTPException
from config import settings
from services.side_camera_service import side_camera_service
from services.side_camera_experiment_recorder import experiment_recorder

router=APIRouter(prefix='/api/experiments',tags=['experiments'])
@router.post('/start')
async def start_experiment():
 status=side_camera_service.status();eid=experiment_recorder.start(status,{"camera_side_transport":settings.CAMERA_SIDE_RTSP_TRANSPORT,"camera_max_frame_gap_ms":settings.CAMERA_MAX_FRAME_GAP_MS,"camera_stale_threshold_ms":settings.CAMERA_STALE_THRESHOLD_MS,"side_experiment_max_fps":settings.SIDE_EXPERIMENT_MAX_FPS})
 if not eid:raise HTTPException(409,'EXPERIMENT_ALREADY_ACTIVE')
 return {'started':True,'experiment_id':eid,'status':experiment_recorder.status()}
@router.get('/status')
async def experiment_status():return experiment_recorder.status()
@router.post('/stop')
async def stop_experiment():
 if not experiment_recorder.stop():raise HTTPException(409,'EXPERIMENT_NOT_ACTIVE')
 return {'stopped':True}
@router.on_event('shutdown')
async def stop_active_experiment():experiment_recorder.stop()
