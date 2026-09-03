"""Permanent, best-effort side-camera capture bound to the production pass id."""
from __future__ import annotations
import csv,json,logging,queue,threading,time
from collections import deque
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit
from config import settings

logger=logging.getLogger(__name__)
FIELDS=('frame_index','filename','captured_monotonic_ns','width','height','receive_wall_time_utc','decode_duration_ms')

def redact_stream_url(value):
 if not value:return None
 try:
  p=urlsplit(value);return f'{p.scheme}://{p.hostname}:{p.port or 554}{p.path or "/..."}'
 except Exception:return 'CONFIGURED_REDACTED'

class SideCameraSessionRecorder:
 def __init__(self,*,enabled=None,configured=None,base_dir=None,target_fps=None,pre_trigger_seconds=None,queue_size=None,shutdown_timeout=None):
  self.enabled=settings.CAMERA_SIDE_ENABLED if enabled is None else bool(enabled);self.configured=bool(settings.CAMERA_SIDE_RTSP_URL or settings.CAMERA_SIDE_RTSP_PATH) if configured is None else bool(configured);self.base_dir=Path(base_dir or settings.SIDE_CAMERA_SESSION_DATA_DIR);self.target_fps=float(target_fps or settings.SIDE_CAMERA_TARGET_FPS);self.shutdown_timeout=float(shutdown_timeout or settings.SIDE_CAMERA_SHUTDOWN_TIMEOUT_SECONDS);self._pre=deque(maxlen=max(1,int((pre_trigger_seconds if pre_trigger_seconds is not None else settings.SIDE_CAMERA_PRE_TRIGGER_SECONDS)*self.target_fps*2)));self._queue=queue.Queue(maxsize=queue_size or settings.SIDE_CAMERA_QUEUE_SIZE);self._lock=threading.RLock();self._thread=None;self._root=None;self._accepting=False;self._seen_seq=set();self._seen_ts=set();self._times=[];self._bytes=0;self._drops=0;self._errors=[];self._resolution=None
 def attach(self,service):service.add_frame_listener(self.record_frame)
 @property
 def active(self):return self._root is not None and self._accepting
 def record_frame(self,sample):
  item=dict(sample)
  with self._lock:
   if not self.active:self._pre.append(item);return
  self._enqueue(item)
 def _enqueue(self,item):
  try:self._queue.put_nowait(item)
  except queue.Full:self._drops+=1
 def start(self,session_id):
  if not self.enabled or not self.configured:return False
  with self._lock:
   if self.active:return self._root.parent.name==session_id
   self._root=self.base_dir/session_id/'camera_side';(self._root/'frames').mkdir(parents=True,exist_ok=True);self._accepting=False;self._seen_seq.clear();self._seen_ts.clear();self._times=[];self._bytes=0;self._drops=0;self._errors=[]
   self._write_manifest('RECORDING');self._thread=threading.Thread(target=self._writer,name='side-camera-session-writer',daemon=True);self._thread.start();buffered=sorted(self._pre,key=lambda x:int(x.get('receive_monotonic_ns',x.get('captured_monotonic_ns',0))))
   for item in buffered:self._enqueue_buffered(item)
   self._accepting=True
  logger.info('SIDE_CAMERA session capture started session=%s buffered=%s',session_id,len(buffered));return True
 def _enqueue_buffered(self,item):
  try:self._queue.put_nowait(item)
  except queue.Full:self._drops+=1
 def _writer(self):
  csv_path=self._root/'frames.csv'
  while True:
   item=self._queue.get()
   if item is None:self._queue.task_done();return
   try:
    seq=int(item.get('frame_counter',item['sequence_number']));ts=int(item.get('receive_monotonic_ns',item['captured_monotonic_ns']))
    if seq in self._seen_seq or ts in self._seen_ts or (self._times and ts<=self._times[-1]):continue
    jpeg=item['jpeg'];name=f'frame_{seq:08d}.jpg';(self._root/'frames'/name).write_bytes(jpeg);wall_ns=item.get('receive_wall_ns');wall=datetime.fromtimestamp(wall_ns/1e9,timezone.utc).isoformat() if wall_ns else datetime.now(timezone.utc).isoformat();decode=item.get('camera_decode_completed_monotonic_ns');read=item.get('camera_frame_read_completed_monotonic_ns');row={'frame_index':seq,'filename':f'frames/{name}','captured_monotonic_ns':ts,'width':int(item.get('width') or 0),'height':int(item.get('height') or 0),'receive_wall_time_utc':wall,'decode_duration_ms':((decode-read)/1e6 if decode and read else '')};new=not csv_path.exists()
    with csv_path.open('a',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,FIELDS);w.writeheader() if new else None;w.writerow(row)
    self._seen_seq.add(seq);self._seen_ts.add(ts);self._times.append(ts);self._bytes+=len(jpeg);self._resolution=(row['width'],row['height'])
   except Exception as exc:self._errors.append(type(exc).__name__);logger.warning('SIDE_CAMERA frame write failed: %s',type(exc).__name__)
   finally:self._queue.task_done()
 def stop(self):
  with self._lock:
   if not self._root:return False
   self._accepting=False
   try:self._queue.put(None,timeout=self.shutdown_timeout)
   except queue.Full:self._errors.append('SHUTDOWN_QUEUE_FULL')
   thread=self._thread
  if thread:thread.join(timeout=self.shutdown_timeout)
  status='PARTIAL' if thread and thread.is_alive() or self._errors else 'COMPLETED';self._write_manifest(status)
  with self._lock:self._root=None;self._thread=None
  return True
 def stop_in_background(self):
  if self._root:threading.Thread(target=self.stop,name='side-camera-session-stopper',daemon=True).start()
 def _manifest(self,status):
  dt=[(b-a)/1e6 for a,b in zip(self._times,self._times[1:]) if b>a];duration=(self._times[-1]-self._times[0])/1e9 if len(self._times)>1 else 0;ordered=sorted(dt);median=ordered[len(ordered)//2] if ordered else None;p95=ordered[min(len(ordered)-1,int(.95*(len(ordered)-1)))] if ordered else None
  fps=(len(self._times)-1)/duration if duration>0 else None;avg_bytes=self._bytes/len(self._times) if self._times else None;mb_min=avg_bytes*fps*60/1_000_000 if avg_bytes and fps else None
  return {'enabled':self.enabled,'configured':self.configured,'stream_url_redacted':redact_stream_url(settings.CAMERA_SIDE_RTSP_URL) or (f'rtsp://{settings.CAMERA_SIDE_HOST}:{settings.CAMERA_SIDE_PORT}/...' if self.configured else None),'target_fps':self.target_fps,'frames_received':len(self._times),'first_frame_monotonic_ns':self._times[0] if self._times else None,'last_frame_monotonic_ns':self._times[-1] if self._times else None,'duration_s':duration,'actual_average_fps':fps,'median_frame_interval_ms':median,'p95_frame_interval_ms':p95,'max_frame_interval_ms':max(dt) if dt else None,'dropped_or_large_gap_count':self._drops+(sum(x>2*median for x in dt) if median else 0),'width':self._resolution[0] if self._resolution else None,'height':self._resolution[1] if self._resolution else None,'average_jpeg_bytes':avg_bytes,'estimated_mb_per_minute':mb_min,'estimated_gb_per_24h_continuous':mb_min*60*24/1000 if mb_min else None,'capture_status':status,'error_summary':sorted(set(self._errors)) or None,'timestamp_semantics':'HOST_RECEIVE_DECODE_MONOTONIC_NOT_CAMERA_EXPOSURE','credentials_stored':False}
 def _write_manifest(self,status):
  if not self._root:return
  p=self._root/'manifest.json';tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(self._manifest(status),indent=2)+'\n',encoding='utf-8');tmp.replace(p)

side_camera_session_recorder=SideCameraSessionRecorder()
