from __future__ import annotations
import hashlib,json,logging,queue,time
from datetime import datetime,timezone
from pathlib import Path
from threading import Lock,Thread
from config import settings

logger=logging.getLogger(__name__)
class SideCameraExperimentRecorder:
 def __init__(self,*,base_dir=None,queue_size=None,max_fps=None,max_bytes=None):
  self.base_dir=Path(base_dir or settings.SIDE_EXPERIMENT_DATA_DIR);self.queue_size=queue_size or settings.SIDE_EXPERIMENT_QUEUE_SIZE;self.max_fps=settings.SIDE_EXPERIMENT_MAX_FPS if max_fps is None else max_fps;self.max_bytes=max_bytes or settings.SIDE_EXPERIMENT_MAX_BYTES
  self._lock=Lock();self._queue=None;self._thread=None;self._dir=None;self._meta={};self._accepting=False;self._bytes=0;self._last_frame_ns=None
 def attach_side_camera(self,service):service.add_frame_listener(self.record_side_frame)
 def attach_lidar(self,buffer):buffer.add_full_profile_listener(self.record_lidar)
 @property
 def active(self):return self._dir is not None and self._accepting
 def start(self,side_status,configuration=None):
  with self._lock:
   if self.active:return None
   wall=time.time_ns();mono=time.monotonic_ns();eid=datetime.now().strftime('%Y-%m-%d_%H-%M-%S')+f'_{wall%1_000_000:06d}';self._dir=self.base_dir/eid;(self._dir/'frames').mkdir(parents=True,exist_ok=False)
   self._queue=queue.Queue(maxsize=self.queue_size);self._bytes=0;self._last_frame_ns=None;self._accepting=True
   self._meta={"experiment_id":eid,"status":"RECORDING","started_wall_ns":wall,"started_monotonic_ns":mono,"stopped_wall_ns":None,"stopped_monotonic_ns":None,"side_camera_enabled":bool(side_status.get('enabled')),"side_camera_transport":side_status.get('transport_requested'),"side_camera_resolution":side_status.get('resolution'),"configuration":configuration or {},"counts":{"side_frames":0,"lidar_profiles":0,"dropped_records":0},"bytes_written":0,"errors":[]}
   self._write_meta();self._thread=Thread(target=self._writer,name='side-experiment-writer',daemon=True);self._thread.start();logger.info('EXPERIMENT_STARTED id=%s',eid);return eid
 def _enqueue(self,kind,payload):
  if not self.active:return
  if self._bytes>=self.max_bytes:self._meta['counts']['dropped_records']+=1;return
  try:self._queue.put_nowait((kind,payload))
  except queue.Full:self._meta['counts']['dropped_records']+=1
 def record_side_frame(self,sample):
  ns=int(sample['receive_monotonic_ns']);minimum=int(1e9/self.max_fps) if self.max_fps>0 else 0
  if self._last_frame_ns is not None and ns-self._last_frame_ns<minimum:return
  self._last_frame_ns=ns;payload={**sample,"recorder_observed_monotonic_ns":time.monotonic_ns()};self._enqueue('side',payload)
 def record_lidar(self,sample):
  if self.active:self._enqueue('lidar',{**sample,"experiment_recorder_observed_monotonic_ns":time.monotonic_ns(),"experiment_recorder_observed_wall_ns":time.time_ns()})
 def _append(self,name,payload):
  data=(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n').encode();
  with (self._dir/name).open('ab') as f:f.write(data)
  self._bytes+=len(data)
 def _writer(self):
  while True:
   item=self._queue.get()
   if item is None:self._queue.task_done();return
   kind,payload=item
   try:
    if kind=='side':
     jpeg=payload.pop('jpeg');name=f"side_{int(payload['frame_counter']):08d}.jpg";(self._dir/'frames'/name).write_bytes(jpeg);self._bytes+=len(jpeg);payload['file']=f'frames/{name}';payload['jpeg_sha256']=hashlib.sha256(jpeg).hexdigest();payload.update({k:None for k in ('vehicle_detected','bbox_x1','bbox_y1','bbox_x2','bbox_y2','landmark_type','landmark_x','landmark_y','tracking_confidence','motion_px_per_sec','diagnostic_state')});self._append('side_frames.jsonl',payload);self._meta['counts']['side_frames']+=1
    else:self._append('lidar_profiles.jsonl',payload);self._meta['counts']['lidar_profiles']+=1
   except Exception as exc:self._meta['errors'].append(type(exc).__name__)
   finally:self._queue.task_done()
 def stop(self):
  with self._lock:
   if not self._dir:return False
   self._accepting=False;self._queue.put(None);self._thread.join();self._meta.update(status='COMPLETED',stopped_wall_ns=time.time_ns(),stopped_monotonic_ns=time.monotonic_ns(),bytes_written=self._bytes);self._write_meta();logger.info('EXPERIMENT_STOPPED id=%s',self._meta['experiment_id']);self._dir=None;self._thread=None;return True
 def _write_meta(self):
  target=self._dir/'metadata.json';tmp=target.with_suffix('.tmp');tmp.write_text(json.dumps(self._meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');tmp.replace(target)
 def status(self):return {"active":self.active,"experiment_id":self._meta.get('experiment_id') if self._dir else None,"directory":str(self._dir) if self._dir else None,"counts":dict(self._meta.get('counts',{}))}

experiment_recorder=SideCameraExperimentRecorder()
