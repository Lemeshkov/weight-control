"""Server adapter for the opt-in provider. Output is diagnostics-only."""
from concurrent.futures import ThreadPoolExecutor
import threading
from config import settings
from services.camera_lidar_diagnostic_recorder import diagnostic_recorder
from services.development_motion_provider import CameraStationaryAnalyzer,DevelopmentMotionProvider,CameraEvidence,CameraState
from services.development_shadow_producers import CameraLifecycleShadowProducer,LidarStrongMovementShadowProducer

WEIGHT_STRONG_MOVEMENT_KG=650.0;WEIGHT_MAX_AGE_MS=1250
class StrongWeightMovementProvider:
 def __init__(self):self.previous=None;self.timestamp_ns=None;self.strong=False
 def update(self,timestamp_ns,weight_kg):
  self.strong=self.previous is not None and abs(float(weight_kg)-self.previous)>=WEIGHT_STRONG_MOVEMENT_KG;self.previous=float(weight_kg);self.timestamp_ns=int(timestamp_ns);return self.strong
 def at(self,timestamp_ns):
  age=None if self.timestamp_ns is None else (int(timestamp_ns)-self.timestamp_ns)/1e6;return bool(self.strong and age is not None and 0<=age<=WEIGHT_MAX_AGE_MS),age

class DevelopmentMotionShadow:
 def __init__(self,enabled=None):
  self.enabled=settings.DEVELOPMENT_MOTION_SHADOW_ENABLED if enabled is None else enabled;self.provider=DevelopmentMotionProvider();self.analyzer=CameraStationaryAnalyzer();self.lifecycle=CameraLifecycleShadowProducer();self.lidar=LidarStrongMovementShadowProducer();self.weight=StrongWeightMovementProvider();self._executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix="development-motion-shadow");self._lidar_executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix="development-lidar-shadow");self._pending=False;self._lidar_pending=False;self._lock=threading.Lock();self._lidar_strong=False;self._lidar_timestamp_ns=None;self._dropped_frames=0;self._dropped_lidar=0
 def attach_camera(self,camera_client):
  if self.enabled:camera_client.add_frame_listener(self.on_camera_frame)
 def attach_lidar(self,lidar_buffer):
  if self.enabled:lidar_buffer.add_full_profile_listener(self.on_full_lidar_profile)
 def camera_enter(self,timestamp_ns):
  if self.enabled:self._emit(self.provider.enter(timestamp_ns),current_production_state="SESSION_OPEN")
 def camera_exit(self,timestamp_ns):
  if self.enabled:self._emit(self.provider.exit(timestamp_ns),current_production_state="SESSION_COMPLETE")
 def update_weight(self,timestamp_ns:int,weight_kg:float):
  if self.enabled:return self.weight.update(timestamp_ns,weight_kg)
  return False
 def update_lidar(self,timestamp_ns:int,strong_movement:bool):self._lidar_strong=bool(strong_movement);self._lidar_timestamp_ns=int(timestamp_ns)
 def on_full_lidar_profile(self,profile):
  if not self.enabled:return
  with self._lock:
   if self._lidar_pending:self._dropped_lidar+=1;return
   self._lidar_pending=True
  self._lidar_executor.submit(self._process_lidar,dict(profile))
 def _process_lidar(self,profile):
  try:
   row=self.lidar.process(profile);self.update_lidar(row["captured_monotonic_ns"],row["strong_sample"]);self._emit(row,event="DEVELOPMENT_LIDAR_MOVEMENT")
  except Exception as exc:self._emit({"captured_monotonic_ns":int(profile.get("captured_monotonic_ns",0) or 0),"strong_movement":False,"unknown_reason":"PROVIDER_EXCEPTION","shadow_error":type(exc).__name__},event="DEVELOPMENT_LIDAR_MOVEMENT")
  finally:
   with self._lock:self._lidar_pending=False
 def on_camera_frame(self,sample):
  if not self.enabled:return
  with self._lock:
   if self._pending:self._dropped_frames+=1;return
   self._pending=True
  self._executor.submit(self._process,dict(sample))
 def _process(self,sample):
  try:
   ts=int(sample["captured_monotonic_ns"]);life=self.lifecycle.process(sample["jpeg"],ts);self._emit(life,event="DEVELOPMENT_CAMERA_LIFECYCLE")
   if life["transition"]=="ENTER":self.camera_enter(ts)
   elif life["transition"]=="EXIT":self.camera_exit(ts)
   e=self.analyzer.process(sample["jpeg"],ts);weight_strong,weight_age=self.weight.at(ts);lidar_age=None if self._lidar_timestamp_ns is None else (ts-self._lidar_timestamp_ns)/1e6;lidar_strong=self._lidar_strong and lidar_age is not None and 0<=lidar_age<=1250;before=self.provider.state.value;row=self.provider.update(e,lidar_strong=lidar_strong,weight_strong=weight_strong);row.update(session_id=diagnostic_recorder.status().get("session_key"),captured_monotonic_ns=ts,shadow_state=row["development_state"],camera_observable=e.state!=CameraState.UNKNOWN,camera_stationary_maturity_ms=row["stationary_maturity_ms"],camera_movement_confirmation=row["movement_confirmation"],lidar_strong_movement=lidar_strong,lidar_persistence_count=self.provider.lidar_strong_count,lidar_age_ms=lidar_age,weight_strong_movement=weight_strong,weight_age_ms=weight_age,transition="" if before==row["development_state"] else before+"->"+row["development_state"],transition_reason=row["reason"],camera_cpu_ms=e.cpu_ms,dropped_camera_frames=self._dropped_frames);self._emit(row,current_production_state="OBSERVE_ONLY")
  except Exception as exc:
   ts=int(sample.get("captured_monotonic_ns",0) or 0);self._emit({**self.provider.update(CameraEvidence(ts,CameraState.UNKNOWN,"SHADOW_EXCEPTION")),"captured_monotonic_ns":ts,"shadow_error":type(exc).__name__},current_production_state="UNAFFECTED")
  finally:
   with self._lock:self._pending=False
 def _emit(self,row,event="DEVELOPMENT_MOTION_SHADOW",**extra):
  if diagnostic_recorder.active:diagnostic_recorder.record_event(event,**row,**extra)
 def shutdown(self):self._executor.shutdown(wait=False,cancel_futures=True);self._lidar_executor.shutdown(wait=False,cancel_futures=True)

development_motion_shadow=DevelopmentMotionShadow()
