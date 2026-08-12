"""Offline custom-detector + ByteTrack vehicle motion research."""

from __future__ import annotations

import argparse
import csv
import json
import time
from collections import Counter, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

try:
    from scripts.analyze_camera_motion import load_frame_rows, read_jsonl, write_csv
    from scripts.validate_camera_motion import duration_metrics, parse_ground_truth, truth_at
except ModuleNotFoundError:
    from analyze_camera_motion import load_frame_rows, read_jsonl, write_csv
    from validate_camera_motion import duration_metrics, parse_ground_truth, truth_at


@dataclass(frozen=True)
class FrozenTrackingCandidate:
    metric: str = "rolling median absolute velocity projected onto PCA trajectory axis"
    stop_threshold_per_sec: float = 0.012
    start_threshold_per_sec: float = 0.035
    rolling_window: int = 5
    stop_confirmation_ms: int = 1500
    resume_confirmation_ms: int = 750
    maximum_short_gap_frames: int = 1
    detector_confidence: float = 0.25
    tracker: str = "bytetrack.yaml"


FIXED_CANDIDATE = FrozenTrackingCandidate()


def dominant_axis(points: list[tuple[float, float]]) -> tuple[float, float]:
    if len(points) < 2: return (0.0, 1.0)
    values=np.asarray(points,float); centered=values-values.mean(axis=0)
    axis=np.linalg.eigh(np.cov(centered.T))[1][:,-1]
    if np.dot(axis, values[-1]-values[0]) < 0: axis=-axis
    return float(axis[0]),float(axis[1])


def iou(a: dict[str, Any], b: dict[str, Any]) -> float:
    x1,y1=max(a["bbox_x1"],b["bbox_x1"]),max(a["bbox_y1"],b["bbox_y1"])
    x2,y2=min(a["bbox_x2"],b["bbox_x2"]),min(a["bbox_y2"],b["bbox_y2"])
    intersection=max(0.,x2-x1)*max(0.,y2-y1)
    union=a["bbox_area"]+b["bbox_area"]-intersection
    return intersection/union if union else 0.


def continuity(track_ids: list[int | None]) -> dict[str, Any]:
    visible=[x for x in track_ids if x is not None]; runs=[]; current=0
    for value in track_ids:
        if value is None: current+=1
        elif current: runs.append(current); current=0
    if current:runs.append(current)
    return {"visible_frames":len(visible),"visibility_fraction":len(visible)/len(track_ids) if track_ids else 0,
            "unique_track_ids":len(set(visible)),"track_switches":sum(a!=b for a,b in zip(visible,visible[1:])),
            "maximum_missing_run":max(runs,default=0)}


def interval_continuity(rows: list[dict[str, Any]], start: int, end: int) -> dict[str, Any]:
    selected = [row for row in rows if start <= row["timestamp_ns"] < end]
    return {"interval_frames": len(selected), **continuity([row["track_id"] for row in selected])}


def choose_track(detections: list[dict[str, Any]], preferred_id: int | None) -> dict[str, Any] | None:
    same=[d for d in detections if d["track_id"]==preferred_id]
    if same:return max(same,key=lambda d:d["confidence"])
    # One-class, fixed overhead ROI: duration/continuity is enforced by preferring the current id.
    return max(detections,key=lambda d:(d["bbox_area"],d["confidence"]),default=None)


class MotionHysteresis:
    def __init__(self,candidate:FrozenTrackingCandidate=FIXED_CANDIDATE):
        self.candidate=candidate; self.state="NO_VEHICLE"; self.wanted=None; self.since=None
    def update(self,timestamp:int,visible:bool,speed:float|None,gap_frames:int=0)->tuple[str,str]:
        if not visible:
            self.wanted=self.since=None
            self.state="TRACK_LOST" if self.state not in {"NO_VEHICLE","TRACK_LOST"} or gap_frames else "NO_VEHICLE"
            return self.state,""
        if self.state in {"NO_VEHICLE","TRACK_LOST"}:self.state="MOVING"
        target="STOPPED" if speed is not None and speed<=self.candidate.stop_threshold_per_sec else \
               "MOVING" if speed is not None and speed>=self.candidate.start_threshold_per_sec else None
        if target==self.state:self.wanted=self.since=None
        elif target:
            if target!=self.wanted:self.wanted,self.since=target,timestamp
            needed=self.candidate.stop_confirmation_ms if target=="STOPPED" else self.candidate.resume_confirmation_ms
            if (timestamp-int(self.since))/1e6>=needed:self.state=target;self.wanted=self.since=None
        return self.state,("STOP_CANDIDATE" if self.wanted=="STOPPED" else "MOVE_CANDIDATE" if self.wanted=="MOVING" else "")


def add_features(rows:list[dict[str,Any]],candidate:FrozenTrackingCandidate=FIXED_CANDIDATE)->tuple[list[dict[str,Any]],tuple[float,float]]:
    visible=[(r["bbox_center_x"],r["bbox_center_y"]) for r in rows if r["visible"]]
    axis=dominant_axis(visible); previous=None; window=deque(maxlen=candidate.rolling_window); fsm=MotionHysteresis(candidate); gap=0
    for row in rows:
        if not row["visible"]:
            gap+=1; row.update({"dx_per_sec":None,"dy_per_sec":None,"center_speed":None,"projected_velocity":None,
                "longitudinal_speed":None,"rolling_longitudinal_speed":None,"leading_edge_velocity":None,
                "trailing_edge_velocity":None,"scale_change_per_sec":None,"bbox_iou":None})
            row["predicted_state"],row["candidate_state"]=fsm.update(row["timestamp_ns"],False,None,gap)
            continue
        gap=0
        if previous:
            dt=max((row["timestamp_ns"]-previous["timestamp_ns"])/1e9,1e-6)
            dx=row["bbox_center_x"]-previous["bbox_center_x"];dy=row["bbox_center_y"]-previous["bbox_center_y"]
            projected=(dx*axis[0]+dy*axis[1])/dt; window.append(abs(projected))
            row.update({"dx_per_sec":dx/dt,"dy_per_sec":dy/dt,"center_speed":float(np.hypot(dx,dy)/dt),
                "projected_velocity":projected,"longitudinal_speed":abs(projected),
                "rolling_longitudinal_speed":float(np.median(window)),
                "leading_edge_velocity":((row["bbox_x2"]-previous["bbox_x2"])*axis[0]+(row["bbox_y2"]-previous["bbox_y2"])*axis[1])/dt,
                "trailing_edge_velocity":((row["bbox_x1"]-previous["bbox_x1"])*axis[0]+(row["bbox_y1"]-previous["bbox_y1"])*axis[1])/dt,
                "scale_change_per_sec":(row["bbox_area"]-previous["bbox_area"])/dt,"bbox_iou":iou(row,previous)})
        else:
            row.update({key:None for key in ("dx_per_sec","dy_per_sec","center_speed","projected_velocity","longitudinal_speed",
                "rolling_longitudinal_speed","leading_edge_velocity","trailing_edge_velocity","scale_change_per_sec","bbox_iou")})
        speed=row["rolling_longitudinal_speed"]
        row["predicted_state"],row["candidate_state"]=fsm.update(row["timestamp_ns"],True,speed)
        previous=row
    return rows,axis


def lidar_simulation(session:Path,timeline:list[dict[str,Any]],scenario:str,markers:dict[str,int]):
    profiles=read_jsonl(session/'lidar'/'raw_scans.jsonl'); result=[]; index=-1
    for n,p in enumerate(profiles):
        timestamp=int(p["captured_monotonic_ns"])
        while index+1<len(timeline) and timeline[index+1]["timestamp_ns"]<=timestamp:index+=1
        predicted=timeline[index]["predicted_state"] if index>=0 else "UNKNOWN"
        actual=truth_at(timestamp,scenario,markers) if markers else "UNKNOWN"
        action="EXCLUDE" if predicted=="NO_VEHICLE" else "ACCEPT" if predicted=="MOVING" else "FREEZE" if predicted=="STOPPED" else "UNKNOWN"
        result.append({"profile_index":n,"timestamp":timestamp,"ground_truth_state":actual,"predicted_state":predicted,"slice_action":action})
    summary={"total_profiles":len(result),"accepted_profiles":sum(r["slice_action"]=="ACCEPT" for r in result),
        "frozen_profiles":sum(r["slice_action"]=="FREEZE" for r in result),"excluded_profiles":sum(r["slice_action"]=="EXCLUDE" for r in result),
        "unknown_profiles":sum(r["slice_action"]=="UNKNOWN" for r in result),
        "moving_profiles_incorrectly_frozen":sum(r["ground_truth_state"]=="MOVING" and r["slice_action"]=="FREEZE" for r in result),
        "stationary_profiles_incorrectly_accepted":sum(r["ground_truth_state"]=="STOPPED" and r["slice_action"]=="ACCEPT" for r in result)}
    return result,summary


def draw_plot(path:Path,rows:list[dict[str,Any]],markers:dict[str,int],candidate:FrozenTrackingCandidate):
    image=np.full((700,1600,3),255,np.uint8)
    if not rows:return
    first,last=rows[0]["timestamp_ns"],rows[-1]["timestamp_ns"];span=max(last-first,1);x=lambda t:60+round((t-first)/span*1480)
    values=[r["rolling_longitudinal_speed"] for r in rows if r["rolling_longitudinal_speed"] is not None];scale=max(np.percentile(values,95) if values else .1,candidate.start_threshold_per_sec)
    y=lambda v:560-round(min((v or 0)/scale,1.2)*400/1.2)
    points=[(x(r["timestamp_ns"]),y(r["rolling_longitudinal_speed"])) for r in rows if r["rolling_longitudinal_speed"] is not None]
    for a,b in zip(points,points[1:]):cv2.line(image,a,b,(190,80,30),2)
    for threshold,color in ((candidate.stop_threshold_per_sec,(0,150,255)),(candidate.start_threshold_per_sec,(170,0,170))):cv2.line(image,(60,y(threshold)),(1540,y(threshold)),color,1)
    for label,t in markers.items():cv2.line(image,(x(t),50),(x(t),620),(0,0,220),2);cv2.putText(image,label,(x(t)+3,70),0,.45,(0,0,180),1)
    for before,after in zip(rows,rows[1:]):
        if before["predicted_state"]!=after["predicted_state"]:cv2.putText(image,after["predicted_state"],(x(after["timestamp_ns"]),640),0,.45,(0,120,0),1)
    cv2.imwrite(str(path),image)


def run(session:Path,scenario:str,weights:Path,output:Path,candidate:FrozenTrackingCandidate=FIXED_CANDIDATE)->dict[str,Any]:
    from ultralytics import YOLO
    frames=load_frame_rows(session,verify_hashes=True); output.mkdir(parents=True,exist_ok=True);(output/'annotated').mkdir(exist_ok=True)
    model=YOLO(str(weights)); rows=[]; preferred=None; age:Counter[int]=Counter(); inference=[]; tracker_overhead=[]; trajectory=[]
    for index,frame in enumerate(frames):
        started=time.perf_counter(); result=model.track(frame["path"],persist=True,tracker=candidate.tracker,conf=candidate.detector_confidence,classes=[0],verbose=False)[0]
        wall=(time.perf_counter()-started)*1000; infer=float(result.speed.get("inference",0));inference.append(infer);tracker_overhead.append(max(0.,wall-infer))
        detections=[]
        if result.boxes.id is not None:
            for xyxy,xywhn,conf,track_id in zip(result.boxes.xyxy.cpu().numpy(),result.boxes.xywhn.cpu().numpy(),result.boxes.conf.cpu().numpy(),result.boxes.id.cpu().numpy()):
                tid=int(track_id);age[tid]+=1;x1,y1,x2,y2=(float(v) for v in xyxy);cx,cy,w,h=(float(v) for v in xywhn)
                detections.append({"track_id":tid,"confidence":float(conf),"bbox_x1":x1/result.orig_shape[1],"bbox_y1":y1/result.orig_shape[0],
                    "bbox_x2":x2/result.orig_shape[1],"bbox_y2":y2/result.orig_shape[0],"bbox_center_x":cx,"bbox_center_y":cy,
                    "bbox_width":w,"bbox_height":h,"bbox_area":w*h,"track_age":age[tid]})
        selected=choose_track(detections,preferred)
        if selected:preferred=selected["track_id"]
        base={"timestamp":frame.get("captured_utc",""),"timestamp_ns":int(frame["captured_monotonic_ns"]),"frame_index":index,
              "file":Path(frame["path"]).name,"visible":selected is not None,"track_lost":selected is None,"yolo_inference_ms":infer,
              "bytetrack_update_ms_estimate":max(0.,wall-infer)}
        rows.append({**base,**(selected or {"track_id":None,"confidence":None,"bbox_x1":None,"bbox_y1":None,"bbox_x2":None,"bbox_y2":None,
            "bbox_center_x":None,"bbox_center_y":None,"bbox_width":None,"bbox_height":None,"bbox_area":None,"track_age":0})})
        if index%10==0:cv2.imwrite(str(output/'annotated'/Path(frame["path"]).name),result.plot())
    started=time.perf_counter();rows,axis=add_features(rows,candidate);trajectory_ms=(time.perf_counter()-started)*1000/len(rows)
    markers,missing=parse_ground_truth(session/'markers.jsonl',scenario); complete=not missing
    for row in rows:row["ground_truth_state"]=truth_at(row["timestamp_ns"],scenario,markers) if complete else "UNKNOWN"
    metric_rows = [{**row, "predicted_state": row["predicted_state"] if row["predicted_state"] in {"MOVING", "STOPPED"} else "UNKNOWN"}
                   for row in rows]
    metric=duration_metrics(metric_rows,scenario,markers if complete else {})
    # Count transitions directly even when no-stop markers are unavailable.
    changes=[b for a,b in zip(rows,rows[1:]) if a["predicted_state"]!=b["predicted_state"]]
    metric["observed_false_stop_transitions_without_complete_ground_truth"]=sum(r["predicted_state"]=="STOPPED" for r in changes) if not complete else None
    if scenario == "stop-resume" and complete:
        stops = [row["timestamp_ns"] for row in changes if row["predicted_state"] == "STOPPED"
                 and markers["VEHICLE_ENTERED"] <= row["timestamp_ns"] < markers["RESUMED"]]
        resumes = [row["timestamp_ns"] for row in changes if row["predicted_state"] == "MOVING"
                   and markers["STOPPED"] <= row["timestamp_ns"] < markers["VEHICLE_EXITED"]]
        metric["first_active_stop_transition_ns"] = stops[0] if stops else None
        metric["signed_stop_transition_offset_ms"] = None if not stops else (stops[0] - markers["STOPPED"]) / 1e6
        metric["first_post_stop_moving_transition_ns"] = resumes[0] if resumes else None
        metric["signed_resume_transition_offset_ms"] = None if not resumes else (resumes[0] - markers["RESUMED"]) / 1e6
    lidar,lidar_summary=lidar_simulation(session,rows,scenario,markers if complete else {})
    write_csv(output/'tracks.csv',rows);write_csv(output/'motion_states.csv',rows);write_csv(output/'lidar_slice_simulation.csv',lidar);draw_plot(output/'tracking_plot.png',rows,markers,candidate)
    active_continuity = interval_continuity(rows, markers["VEHICLE_ENTERED"], markers["VEHICLE_EXITED"]) if complete else None
    report={"session_key":session.name,"dataset_role":"DEVELOPMENT","scenario":scenario,"ground_truth":{"complete":complete,"missing":missing,**markers},
        "model":str(weights),"detector_test_recall":0.9411764705882353,"candidate":asdict(candidate),"dominant_axis":axis,
        "tracking_continuity":continuity([r["track_id"] for r in rows]),"active_interval_continuity":active_continuity,
        "metrics":metric,"lidar_slice_simulation":lidar_summary,
        "performance":{"device":"CPU","frames":len(rows),"yolo_inference_ms_median":float(np.median(inference)),
            "bytetrack_plus_io_overhead_ms_median":float(np.median(tracker_overhead)),"trajectory_processing_ms_per_frame":trajectory_ms,
            "estimated_capacity_fps":1000/float(np.median(inference)+np.median(tracker_overhead)+trajectory_ms),"5_fps_budget_ms":200,"10_fps_budget_ms":100,"20_fps_budget_ms":50},
        "research_result":"TRACKING NOT SUITABLE"}
    (output/'tracking_summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8');return report


def main():
    parser=argparse.ArgumentParser();parser.add_argument('session',type=Path);parser.add_argument('--scenario',choices=('stop-resume','no-stop'),required=True)
    parser.add_argument('--weights',type=Path,required=True);parser.add_argument('--output',type=Path)
    args=parser.parse_args();output=args.output or args.session/'vehicle_motion_tracking';report=run(args.session.resolve(),args.scenario,args.weights.resolve(),output.resolve())
    print(json.dumps({"session":report["session_key"],"output":str(output),"continuity":report["tracking_continuity"],"metrics":report["metrics"],"performance":report["performance"]},indent=2))


if __name__=='__main__':main()
