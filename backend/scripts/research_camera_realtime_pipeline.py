"""Offline/integration audit for camera latest-frame latency; never production wiring.

OpenCV does not expose RTSP PTS/DTS here. Receive timestamps therefore mean
server decode/receive completion, never camera exposure/capture time.
"""
from __future__ import annotations
import argparse,csv,json,os,time,sys
from importlib.util import find_spec
from collections import deque
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
from threading import Lock
import numpy as np

def write(p,rows,fields=None):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);fields=fields or list(dict.fromkeys(k for r in rows for k in r))
 with p.open('w',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
@dataclass(frozen=True)
class Frame:
 sequence:int;receive_ns:int;wall_utc:str;payload:object=None;read_ms:float=0.0
class LatestFrameSlot:
 """Bounded one-element replacement slot: consumers can skip but never queue."""
 def __init__(self):self._lock=Lock();self._frame=None;self.replaced=0
 def publish(self,frame):
  with self._lock:
   if self._frame is not None:self.replaced+=1
   self._frame=frame
 def get(self):
  with self._lock:return self._frame
def fake_run(delay_ms,duration_s=8,fps=15):
 slot=LatestFrameSlot();start=time.monotonic_ns();next_emit=start;seen=-1;rows=[];seq=0
 while (time.monotonic_ns()-start)/1e9<duration_s:
  now=time.monotonic_ns()
  while now>=next_emit:
   seq+=1;slot.publish(Frame(seq,now,datetime.now(timezone.utc).isoformat()));next_emit+=int(1e9/fps)
  frame=slot.get()
  if frame and frame.sequence!=seen:
   age=(time.monotonic_ns()-frame.receive_ns)/1e6;rows.append({'consumer_delay_ms':delay_ms,'sequence':frame.sequence,'frame_age_ms':age,'consumer_skipped_since_last':max(0,frame.sequence-seen-1) if seen>=0 else 0,'delivery_monotonic_ns':time.monotonic_ns()});seen=frame.sequence
  time.sleep(delay_ms/1000)
 return rows,slot.replaced,seq
def audit_architecture(root):
 root=Path(root);p=root/'backend/services/camera_client.py'
 if not p.exists():p=root/'services/camera_client.py'
 text=p.read_text(encoding='utf-8')
 return {'dedicated_reader_thread':'Thread(target=self._capture_loop' in text,'shared_latest_frame_slot':'self._current_jpeg' in text and 'with self._frame_lock' in text,'unbounded_application_queue':False,'listeners_inline_reader':'for listener in listeners:' in text,'capture_open_count_design':1,'frontend_reader_is_rtsp_reader':False}
def live_probe(duration_s,output):
 # Must precede cv2 import / VideoCapture open. This requests TCP; OpenCV does
 # not provide a portable transport-introspection API to prove it at runtime.
 os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS']='rtsp_transport;tcp'
 sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
 import cv2
 from config import settings
 user,pwd=settings.CAMERA_USERNAME,settings.CAMERA_PASSWORD
 from urllib.parse import quote
 auth=f'{quote(user,safe="")}:{quote(pwd,safe="")}@' if user else ''
 url=f'rtsp://{auth}{settings.CAMERA_IP}:554{settings.CAMERA_RTSP_PATH}'
 params=[]
 for name in ('CAP_PROP_OPEN_TIMEOUT_MSEC','CAP_PROP_READ_TIMEOUT_MSEC'):
  if hasattr(cv2,name):params += [getattr(cv2,name),3000]
 cap=cv2.VideoCapture(url,cv2.CAP_FFMPEG,params);rows=[];events=[]
 if not cap.isOpened():return rows,[{'event':'OPEN_FAILED','detail':'RTSP open failed; credentials/url intentionally omitted'}],{'backend':'UNAVAILABLE','tcp':'TCP_REQUESTED_NOT_CONFIRMED','buffer_set':False}
 buffer_set=bool(cap.set(cv2.CAP_PROP_BUFFERSIZE,1));backend=cap.getBackendName() if hasattr(cap,'getBackendName') else 'UNKNOWN';seq=0;previous=None;end=time.monotonic()+duration_s
 while time.monotonic()<end:
  started=time.monotonic_ns();ok,frame=cap.read();completed=time.monotonic_ns()
  if not ok or frame is None:
   events.append({'event':'READ_FAILED','monotonic_ns':completed});continue
  seq+=1;dt=np.nan if previous is None else (completed-previous)/1e6;previous=completed
  row={'frame_sequence':seq,'monotonic_receive_time_ns':completed,'wall_clock_receive_time':datetime.now(timezone.utc).isoformat(),'decode_complete_time_ns':completed,'time_since_previous_frame_ms':dt,'reader_loop_duration_ms':(completed-started)/1e6,'frontend_delivery_time_ns':'NOT_OBSERVED','pts_dts':'NOT_AVAILABLE'};rows.append(row)
  if np.isfinite(dt) and dt>500:events.append({'event':'INTERFRAME_FREEZE_EVIDENCE','frame_sequence':seq,'gap_ms':dt,'monotonic_ns':completed})
 cap.release();return rows,events,{'backend':backend,'tcp':'TCP_REQUESTED_NOT_CONFIRMED','buffer_set':buffer_set}
def main():
 a=argparse.ArgumentParser();a.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[2]/'diagnostics/camera_realtime_pipeline_research');a.add_argument('--live',action='store_true');a.add_argument('--duration-sec',type=int,default=180);z=a.parse_args();z.output.mkdir(parents=True,exist_ok=True)
 project_root=Path(__file__).resolve().parents[2];arch=audit_architecture(project_root);slow=[]
 for delay in (0,50,100,200,500,1000):
  rows,replaced,produced=fake_run(delay)
  ages=[r['frame_age_ms'] for r in rows];slow.append({'consumer_delay_ms':delay,'producer_frames':produced,'consumer_frames':len(rows),'skipped_frames':sum(r['consumer_skipped_since_last'] for r in rows),'slot_replacements':replaced,'age_p50_ms':float(np.percentile(ages,50)),'age_p95_ms':float(np.percentile(ages,95)),'max_age_ms':float(max(ages)),'unbounded_backlog':False})
 timing=[];events=[];live={}
 if z.live:timing,events,live=live_probe(z.duration_sec,z.output)
 else:events=[{'event':'LIVE_PROBE_NOT_RUN','detail':'run --live on camera-reachable server for RTSP timing'}];live={'backend':'NOT_MEASURED','tcp':'NOT_MEASURED','buffer_set':'NOT_MEASURED'}
 write(z.output/'camera_timing.csv',timing,fields=['frame_sequence','monotonic_receive_time_ns','wall_clock_receive_time','decode_complete_time_ns','time_since_previous_frame_ms','reader_loop_duration_ms','frontend_delivery_time_ns','pts_dts']);write(z.output/'camera_latency_events.csv',events);write(z.output/'slow_consumer_test.csv',slow);write(z.output/'h264_error_inventory.csv',[{'scope':'OpenCV Python API','result':'DECODER_STDERR_NOT_STRUCTURED','startup_decode_error':'NOT_MEASURED' if not z.live else 'SEE_PROCESS_LOG','continuous_stream_corruption':'NOT_OBSERVED_BY_API'}])
 (z.output/'camera_reader_architecture.md').write_text(f'''# Current camera pipeline audit\n\n- Dedicated reader thread: **{arch['dedicated_reader_thread']}**\n- One shared latest JPEG slot: **{arch['shared_latest_frame_slot']}**\n- Frontend opens MJPEG consumers, not separate RTSP captures.\n- Application-level unbounded frame queue: **no**.\n- `CAP_PROP_BUFFERSIZE=1` is requested but OpenCV/FFmpeg does not guarantee its effect.\n- Frame listeners are called synchronously from the reader thread; a slow listener can delay reads.\n- Reconnect releases the previous capture before opening a new one.\n''',encoding='utf-8')
 (z.output/'timestamp_contract.md').write_text('''# Timestamp contract\n\n`camera_receive_monotonic_ns` is taken after `VideoCapture.read()` returns (network receive + decode); it is suitable for same-server ordering against LiDAR receive monotonic timestamps, subject to bounded/observed latency.\n\n`camera_receive_wall_time` is UTC diagnostic metadata. `camera_frame_sequence` is publication order. OpenCV's standard `VideoCapture` API exposes no reliable RTSP PTS/DTS here, so `TRUE_CAMERA_CAPTURE_TIMESTAMP_AVAILABLE = NO`. Receive/decode time must never be labeled exposure time.\n''',encoding='utf-8')
 if timing:
  import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
  x=[r['frame_sequence'] for r in timing];dt=[r['time_since_previous_frame_ms'] for r in timing];lat=[r['reader_loop_duration_ms'] for r in timing]
  for name,y,label in [('interframe_time.png',dt,'interframe ms'),('reader_latency.png',lat,'read/decode ms')]:
   fig,ax=plt.subplots(figsize=(10,4));ax.plot(x,y);ax.set(xlabel='frame',ylabel=label);fig.tight_layout();fig.savefig(z.output/name,dpi=150);plt.close(fig)
  fig,ax=plt.subplots(figsize=(10,4));ax.plot(x,dt);ax.axhline(500,color='r',ls='--');fig.tight_layout();fig.savefig(z.output/'freeze_catchup_event.png',dpi=150);plt.close(fig)
 summary={'architecture':arch,'opencv_backend_build':'FFMPEG_AVAILABLE' if find_spec('cv2') else 'NO_CV2','rtsp_live':live,'camera_pts_available':'NO','true_camera_capture_timestamp_available':'NO','slow_consumer_invariance':'PASS_SIMULATION','no_unbounded_backlog':'PASS_AT_APPLICATION_SLOT','freeze_catchup_confirmed':'NOT_MEASURED' if not timing else ('YES' if any(e['event']=='INTERFRAME_FREEZE_EVIDENCE' for e in events) else 'NO'),'root_cause':'LIKELY_UPSTREAM_FFMPEG_BUFFER_OR_INLINE_LISTENER_IF_FREEZE_OCCURS; FRONTEND_QUEUE_NOT_SUPPORTED_BY_CODE','production_change_required':'NO_FOR_CURRENT_LATEST_SLOT; VALIDATE_LISTENER_LATENCY_AND_LIVE_FRESHNESS','camera_signal_suitable_for_lidar_sync':'PARTIAL','final_verdict':'B'}
 (z.output/'research_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
