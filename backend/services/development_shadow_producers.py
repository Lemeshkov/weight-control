"""Shadow-only Camera lifecycle and frozen strong-LiDAR movement producers."""
from collections import deque
import cv2,numpy as np

FOREGROUND_DIFFERENCE_THRESHOLD=.08;PRESENCE_AREA_RATIO=.03;ENTER_FRAMES=3;EXIT_FRAMES=8
LIDAR_CLEAR_SCORE=2.0;LIDAR_GAP_MS=1200;LIDAR_STRONG_PROFILES=2
ZONES={f"z{x}_{x+10}":(x,x+10) for x in range(20,80)}
class CameraLifecycleShadowProducer:
 def __init__(self):self.background_frames=[];self.background=None;self.present=False;self.present_count=0;self.absent_count=0
 def process(self,jpeg,timestamp_ns):
  image=cv2.imdecode(np.frombuffer(jpeg,np.uint8),0) if isinstance(jpeg,(bytes,bytearray)) else jpeg
  if image is None:return self._row(timestamp_ns,None,0,"NONE","DECODE_ERROR")
  image=cv2.resize(image,(320,180))
  if self.background is None:
   self.background_frames.append(image.astype(np.float32))
   if len(self.background_frames)>=5:self.background=np.median(np.stack(self.background_frames),axis=0).astype(np.uint8)
   return self._row(timestamp_ns,None,0,"NONE","BACKGROUND_BOOTSTRAP")
  diff=cv2.absdiff(image,self.background).astype(np.float32)/255.;mask=(diff>=FOREGROUND_DIFFERENCE_THRESHOLD).astype(np.uint8);mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((3,3),np.uint8));area=float(np.mean(mask));detected=area>=PRESENCE_AREA_RATIO;transition="NONE";reason="PRESENCE" if detected else "ABSENCE"
  if detected:self.present_count+=1;self.absent_count=0
  else:self.absent_count+=1;self.present_count=0
  if not self.present and self.present_count>=ENTER_FRAMES:self.present=True;transition="ENTER";reason="PERSISTENT_CAMERA_PRESENCE"
  elif self.present and self.absent_count>=EXIT_FRAMES:self.present=False;transition="EXIT";reason="PERSISTENT_CAMERA_ABSENCE";self.background_frames=[image.astype(np.float32)];self.background=None
  return self._row(timestamp_ns,detected,min(1.,area/max(PRESENCE_AREA_RATIO,1e-9)),transition,reason,area)
 def _row(self,t,presence,confidence,transition,reason,area=None):return {"captured_monotonic_ns":int(t),"presence":presence,"presence_confidence":confidence,"presence_persistence":self.present_count if presence else self.absent_count,"transition":transition,"reason":reason,"foreground_area_ratio":area}

def _zone_indices(profile,start,end):
 angles=profile["start_angle_deg"]+np.arange(profile["beam_count"])*profile["angular_step_deg"];return np.flatnonzero((angles>=start)&(angles<=end))
def _pair(a,b,idx):
 x,y=a[idx],b[idx];valid=np.isfinite(x)&np.isfinite(y)
 if valid.sum()<4:return None
 x,y=x[valid],y[valid];d=x-y;ac=x-np.median(x);bc=y-np.median(y);den=np.linalg.norm(ac)*np.linalg.norm(bc);return float(np.percentile(np.abs(d),90)),float(np.dot(ac,bc)/den) if den else 1.
def _window(profiles,idx):
 if len(profiles)<3:return None
 stack=np.vstack([p["values"][idx] for p in profiles]);valid=np.sum(np.isfinite(stack),axis=0)>=max(3,int(len(profiles)*.7))
 if valid.sum()<4:return None
 data=stack[:,valid];var=np.nanstd(data,axis=0);diff=np.diff(data,axis=0);cum=np.nansum(np.abs(diff),axis=0);steps=np.sum(np.isfinite(diff),axis=0);cons=np.abs(np.nansum(np.sign(diff),axis=0))/np.maximum(steps,1);return float(np.nanpercentile(var,90)),float(np.nanpercentile(cum,90)),float(np.nanmedian(cons))
class LidarStrongMovementShadowProducer:
 def __init__(self):self.history=deque();self.previous_ts=None;self.strong_count=0
 def process(self,profile):
  t=int(profile["captured_monotonic_ns"]);gap=None if self.previous_ts is None else (t-self.previous_ts)/1e6;self.previous_ts=t
  if gap is not None and gap>=LIDAR_GAP_MS:self.history.clear();self.strong_count=0;return self._row(t,False,{},gap,"SENSOR_GAP")
  values=np.array([np.nan if x is None else x for x in profile["ranges_mm"]],float);p={**profile,"values":values};self.history.append(p)
  # Keep enough causal history to retain the sample immediately preceding the
  # frozen 5 s baseline at a valid (< sensor-gap) acquisition cadence.
  while self.history and t-int(self.history[0]["captured_monotonic_ns"])>5_000_000_000+LIDAR_GAP_MS*1_000_000:self.history.popleft()
  evidence={};scores=[]
  for name,bounds in ZONES.items():
   idx=_zone_indices(p,*bounds);components=[]
   for lag in (1000,2000,3000,5000):
    old=next((x for x in reversed(self.history) if int(x["captured_monotonic_ns"])<=t-lag*1_000_000),None)
    if old is not None:
     q=_pair(values,old["values"],idx)
     if q is not None:components.append(min(q[0]/10,20)+max(0,1-q[1])*20)
   members=[x for x in self.history if int(x["captured_monotonic_ns"])>=t-3_000_000_000];w=_window(members,idx)
   if w is not None:components.extend((min(w[0]/4,20),min(w[1]/20,20)*w[2]))
   score=float(np.median(components)) if components else None;evidence[name]=score
   if score is not None:scores.append(score)
  strong_sample=any(v is not None and v>=LIDAR_CLEAR_SCORE for v in evidence.values());self.strong_count=self.strong_count+1 if strong_sample else 0
  return self._row(t,self.strong_count>=LIDAR_STRONG_PROFILES,evidence,gap,"STRONG_PERSISTENCE" if self.strong_count>=2 else "STRONG_PENDING" if strong_sample else "NO_STRONG_PROGRESSION",strong_sample)
 def _row(self,t,strong,zones,gap,reason,strong_sample=False):return {"captured_monotonic_ns":t,"strong_movement":strong,"strong_sample":strong_sample,"strong_count":self.strong_count,"zone_evidence":zones,"profile_age_ms":0,"gap_ms":gap,"unknown_reason":"SENSOR_GAP" if reason=="SENSOR_GAP" else "","reason":reason}
