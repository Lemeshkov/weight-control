"""Opt-in DEVELOPMENT shadow motion provider; never owns production actions."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import math,time
import cv2,numpy as np

STOP_MATURITY_MS=3000;CAMERA_MOVE_MS=450;MAX_CAMERA_GAP_MS=550
LOW_MOTION=0.0007509146619165779;HIGH_MOTION=0.0015554660853986256;MAX_ANCHOR_DRIFT=0.006
MIN_FEATURES=8;COAL_ROI=(.36,.28,.68,.78);BACKGROUND_ROIS=((.04,.30,.22,.72),(.80,.30,.96,.72))
class MotionState(str,Enum):
 NO_VEHICLE="NO_VEHICLE";MOVING="VEHICLE_PRESENT_MOVING";CANDIDATE="STOP_CANDIDATE";STOPPED="PHYSICAL_STOPPED";COMPLETE="SESSION_COMPLETE"
class CameraState(str,Enum):UNKNOWN="UNKNOWN";STATIONARY="STATIONARY_POSITIVE";MOVING="MOVEMENT"
@dataclass(frozen=True)
class CameraEvidence:
 timestamp_ns:int;state:CameraState;reason:str="";anchor_id:int|None=None;anchor_displacement:float|None=None;features:int=0;cpu_ms:float=0
class DevelopmentMotionProvider:
 def __init__(self):self.reset()
 def reset(self):
  self.state=MotionState.NO_VEHICLE;self.stationary_since=None;self.camera_move_since=None;self.camera_move_confirmed=False;self.movement_confirmation=False;self.movement_episode_id=0;self.lidar_strong_count=0;self.last_camera=CameraState.UNKNOWN;self.last_reason="NO_SESSION";self.anchor_id=None;self.anchor_displacement=None
 def enter(self,timestamp_ns:int):self.reset();self.state=MotionState.MOVING;self.last_reason="CAMERA_ENTER";return self.snapshot(timestamp_ns)
 def exit(self,timestamp_ns:int):self.state=MotionState.COMPLETE;self.stationary_since=None;self.last_reason="CAMERA_EXIT";return self.snapshot(timestamp_ns)
 def update(self,e:CameraEvidence,*,lidar_strong=False,weight_strong=False):
  if self.state in (MotionState.NO_VEHICLE,MotionState.COMPLETE):return self.snapshot(e.timestamp_ns)
  self.last_camera=e.state;self.anchor_id=e.anchor_id;self.anchor_displacement=e.anchor_displacement;self.movement_confirmation=False
  if lidar_strong:self.lidar_strong_count+=1
  else:self.lidar_strong_count=0
  lidar_movement=self.lidar_strong_count>=2
  if weight_strong or lidar_movement:
   self.stationary_since=None;self.camera_move_since=None;self.camera_move_confirmed=False;self.movement_confirmation=True;self.movement_episode_id+=1;self.state=MotionState.MOVING;self.last_reason="WEIGHT_MOVEMENT" if weight_strong else "SUSTAINED_LIDAR_MOVEMENT";return self.snapshot(e.timestamp_ns,lidar_movement,weight_strong)
  if e.state==CameraState.UNKNOWN:
   self.stationary_since=None;self.camera_move_since=None;self.camera_move_confirmed=False;self.last_reason="CAMERA_UNKNOWN:"+e.reason
   if self.state==MotionState.CANDIDATE:self.state=MotionState.MOVING
  elif e.state==CameraState.MOVING:
   self.stationary_since=None
   if self.camera_move_since is None:self.camera_move_since=e.timestamp_ns
   if self.state==MotionState.CANDIDATE:self.state=MotionState.MOVING
   if not self.camera_move_confirmed and (e.timestamp_ns-self.camera_move_since)/1e6>=CAMERA_MOVE_MS:self.camera_move_confirmed=True;self.movement_confirmation=True;self.movement_episode_id+=1;self.state=MotionState.MOVING;self.last_reason="SUSTAINED_CAMERA_MOVEMENT"
   if not self.movement_confirmation:self.last_reason="CAMERA_MOVEMENT"
  else:
   self.camera_move_since=None;self.camera_move_confirmed=False
   if self.stationary_since is None:self.stationary_since=e.timestamp_ns
   maturity=(e.timestamp_ns-self.stationary_since)/1e6
   if maturity>=STOP_MATURITY_MS:self.state=MotionState.STOPPED;self.last_reason="CAMERA_STATIONARY_3000MS"
   elif self.state!=MotionState.STOPPED:self.state=MotionState.CANDIDATE;self.last_reason="CAMERA_STATIONARY_ACCUMULATING"
  return self.snapshot(e.timestamp_ns,lidar_movement,weight_strong)
 def snapshot(self,timestamp_ns,lidar=False,weight=False):
  maturity=0 if self.stationary_since is None else max(0,(timestamp_ns-self.stationary_since)/1e6)
  return {"timestamp_ns":timestamp_ns,"camera_state":self.last_camera.value,"lidar_movement_veto":bool(lidar),"weight_movement_veto":bool(weight),"provisional_anchor_id":self.anchor_id,"anchor_displacement":self.anchor_displacement,"stationary_maturity_ms":maturity,"development_state":self.state.value,"reason":self.last_reason,"unknown_reason":self.last_reason.split(":",1)[1] if self.last_reason.startswith("CAMERA_UNKNOWN:") else "","movement_confirmation":self.movement_confirmation,"movement_episode_id":self.movement_episode_id,"production_action_triggered":False}

def _rect(shape,r):h,w=shape[:2];return int(r[0]*w),int(r[1]*h),int(r[2]*w),int(r[3]*h)
def _pts(g,r,n):
 m=np.zeros(g.shape,np.uint8);x1,y1,x2,y2=_rect(g.shape,r);m[y1:y2,x1:x2]=255;return cv2.goodFeaturesToTrack(g,n,.01,5,mask=m,blockSize=5)
def _median(v):
 if not len(v):return np.zeros(2),np.zeros(0,bool)
 med=np.median(v,axis=0);d=np.linalg.norm(v-med,axis=1);return med,d<=max(1.5,np.percentile(d,75))
class CameraStationaryAnalyzer:
 def __init__(self):self.previous=None;self.previous_ts=None;self.cumulative=np.zeros(2);self.anchor=None;self.anchor_id=0;self.texture_present=False
 def reset_anchor(self):self.anchor=None
 def process(self,jpeg:bytes|np.ndarray,timestamp_ns:int)->CameraEvidence:
  started=time.perf_counter();g=cv2.imdecode(np.frombuffer(jpeg,np.uint8),0) if isinstance(jpeg,(bytes,bytearray)) else jpeg
  if g is None:return CameraEvidence(timestamp_ns,CameraState.UNKNOWN,"DECODE",cpu_ms=(time.perf_counter()-started)*1000)
  g=cv2.resize(g,None,fx=.5,fy=.5,interpolation=cv2.INTER_AREA)
  if self.previous is None:self.previous=g;self.previous_ts=timestamp_ns;return CameraEvidence(timestamp_ns,CameraState.UNKNOWN,"FIRST_FRAME")
  dt=(timestamp_ns-self.previous_ts)/1e9;old=self.previous;self.previous=g;self.previous_ts=timestamp_ns
  if dt<=0 or dt*1000>MAX_CAMERA_GAP_MS:self.reset_anchor();return CameraEvidence(timestamp_ns,CameraState.UNKNOWN,"CAMERA_GAP",cpu_ms=(time.perf_counter()-started)*1000)
  coal=_rect(g.shape,COAL_ROI);regions=(COAL_ROI,*BACKGROUND_ROIS);sets=[_pts(old,r,180 if i==0 else 60) for i,r in enumerate(regions)];sets=[p for p in sets if p is not None]
  if not sets:self.reset_anchor();return CameraEvidence(timestamp_ns,CameraState.UNKNOWN,"POOR_FEATURES",cpu_ms=(time.perf_counter()-started)*1000)
  p=np.vstack(sets);q,st,_=cv2.calcOpticalFlowPyrLK(old,g,p,None,winSize=(21,21),maxLevel=3);back,st2,_=cv2.calcOpticalFlowPyrLK(g,old,q,None,winSize=(21,21),maxLevel=3);good=(st.ravel()==1)&(st2.ravel()==1)&(np.linalg.norm(back-p,axis=2).ravel()<1.5);orig=p[good].reshape(-1,2);vec=(q[good]-p[good]).reshape(-1,2)
  def inside(r):x1,y1,x2,y2=_rect(g.shape,r);return (orig[:,0]>=x1)&(orig[:,0]<x2)&(orig[:,1]>=y1)&(orig[:,1]<y2)
  cv=vec[inside(COAL_ROI)];bv=vec[np.logical_or.reduce([inside(r) for r in BACKGROUND_ROIS])];cm,ck=_median(cv);bm,bk=_median(bv);features=int(ck.sum());bgfeatures=int(bk.sum())
  if features<MIN_FEATURES or bgfeatures<4:self.reset_anchor();return CameraEvidence(timestamp_ns,CameraState.UNKNOWN,"COAL_ROI_ABSENT_OR_POOR" if features<MIN_FEATURES else "POOR_BACKGROUND",features=features,cpu_ms=(time.perf_counter()-started)*1000)
  diag=math.hypot(*g.shape);rel=(cm-bm)/diag;speed=float(np.linalg.norm(rel)/dt);coherent=max(np.mean(cv@cm>0),np.mean(cv@cm<0)) if np.linalg.norm(cm)>0 else 0
  x1,y1,x2,y2=coal;zones=[(x1,y1,x1+(x2-x1)//3,y2),(x1+(x2-x1)//3,y1,x1+2*(x2-x1)//3,y2),(x1+2*(x2-x1)//3,y1,x2,y2)];zs=[]
  for z in zones:
   mask=(orig[:,0]>=z[0])&(orig[:,0]<z[2])&(orig[:,1]>=z[1])&(orig[:,1]<z[3]);zm,zk=_median(vec[mask]);zs.append(float(np.linalg.norm((zm-bm)/diag)/dt) if zk.sum()>=4 else None)
  moving=speed>=HIGH_MOTION and coherent>=.6 and sum(v is not None and v>=HIGH_MOTION for v in zs)>=2
  if moving:self.texture_present=True;self.reset_anchor();self.cumulative+=rel*dt;return CameraEvidence(timestamp_ns,CameraState.MOVING,"COHERENT_MULTI_ZONE",features=features,cpu_ms=(time.perf_counter()-started)*1000)
  if not self.texture_present:self.reset_anchor();return CameraEvidence(timestamp_ns,CameraState.UNKNOWN,"COAL_ROI_NOT_YET_OBSERVED",features=features,cpu_ms=(time.perf_counter()-started)*1000)
  self.cumulative+=rel*dt;stationary=speed<=LOW_MOTION and sum(v is not None and v<=LOW_MOTION for v in zs)>=2
  if not stationary:self.reset_anchor();return CameraEvidence(timestamp_ns,CameraState.UNKNOWN,"HYSTERESIS",features=features,cpu_ms=(time.perf_counter()-started)*1000)
  if self.anchor is None:self.anchor=self.cumulative.copy();self.anchor_id+=1
  drift=float(np.linalg.norm(self.cumulative-self.anchor))
  if drift>MAX_ANCHOR_DRIFT:self.reset_anchor();return CameraEvidence(timestamp_ns,CameraState.UNKNOWN,"ANCHOR_CUMULATIVE_DRIFT",self.anchor_id,drift,features,(time.perf_counter()-started)*1000)
  return CameraEvidence(timestamp_ns,CameraState.STATIONARY,"",self.anchor_id,drift,features,(time.perf_counter()-started)*1000)
