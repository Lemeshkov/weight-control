"""Offline YOLO detection audit and conditional vehicle tracking research."""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

try:
    from scripts.analyze_camera_motion import load_frame_rows, read_jsonl, write_csv
    from scripts.validate_camera_motion import parse_ground_truth, truth_at
except ModuleNotFoundError:
    from analyze_camera_motion import load_frame_rows, read_jsonl, write_csv
    from validate_camera_motion import parse_ground_truth, truth_at


VEHICLE_CLASS_IDS = (2, 5, 7)
VEHICLE_CLASS_NAMES = {2: "car", 5: "bus", 7: "truck"}
AUDIT_CONFIDENCE = 0.10
WORKING_CONFIDENCE = 0.25
MINIMUM_DETECTION_RATE_FOR_TRACKING = 0.80
MODEL_NAME = "yolo11n.pt"
INPUT_SIZE = 640


def dominant_trajectory_axis(points: list[tuple[float, float]]) -> tuple[float, float]:
    if len(points) < 2: return (0.0, 1.0)
    values = np.asarray(points, dtype=float); centered = values - np.mean(values, axis=0)
    axis = np.linalg.eigh(np.cov(centered.T))[1][:, -1]
    if np.dot(axis, values[-1] - values[0]) < 0: axis = -axis
    return float(axis[0]), float(axis[1])


def normalized_bbox_features(previous: dict[str, float], current: dict[str, float], dt_seconds: float,
                             axis: tuple[float, float]) -> dict[str, float]:
    dt = max(dt_seconds, 1e-6)
    dx = current["center_x"] - previous["center_x"]; dy = current["center_y"] - previous["center_y"]
    return {"dx_per_sec": dx / dt, "dy_per_sec": dy / dt,
            "center_speed": math.hypot(dx, dy) / dt,
            "projected_velocity": (dx * axis[0] + dy * axis[1]) / dt,
            "leading_edge_velocity": ((current["y2"] - previous["y2"]) * axis[1] + (current["x2"] - previous["x2"]) * axis[0]) / dt,
            "trailing_edge_velocity": ((current["y1"] - previous["y1"]) * axis[1] + (current["x1"] - previous["x1"]) * axis[0]) / dt,
            "scale_change_per_sec": ((current["width"] * current["height"]) - (previous["width"] * previous["height"])) / dt,
            "bbox_iou": bbox_iou(previous, current)}


def bbox_iou(left: dict[str, float], right: dict[str, float]) -> float:
    x1, y1 = max(left["x1"], right["x1"]), max(left["y1"], right["y1"])
    x2, y2 = min(left["x2"], right["x2"]), min(left["y2"], right["y2"])
    intersection = max(0.0, x2-x1) * max(0.0, y2-y1)
    union = left["width"]*left["height"] + right["width"]*right["height"] - intersection
    return intersection / union if union else 0.0


@dataclass
class TrajectoryHysteresis:
    stop_speed: float
    start_speed: float
    stop_confirmation_ms: int
    resume_confirmation_ms: int
    state: str = "NO_VEHICLE"
    candidate: str | None = None
    candidate_since_ns: int | None = None

    def update(self, timestamp_ns: int, *, visible: bool, speed: float | None) -> str:
        if not visible or speed is None:
            self.state = "TRACK_LOST" if self.state not in {"NO_VEHICLE", "TRACK_LOST"} else "NO_VEHICLE"
            self.candidate = self.candidate_since_ns = None
            return self.state
        if self.state in {"NO_VEHICLE", "TRACK_LOST"}: self.state = "MOVING"
        wanted = "STOPPED" if speed <= self.stop_speed else "MOVING" if speed >= self.start_speed else None
        if wanted == self.state: self.candidate = self.candidate_since_ns = None
        elif wanted:
            if self.candidate != wanted: self.candidate, self.candidate_since_ns = wanted, timestamp_ns
            required = self.stop_confirmation_ms if wanted == "STOPPED" else self.resume_confirmation_ms
            if (timestamp_ns - int(self.candidate_since_ns)) / 1e6 >= required:
                self.state = wanted; self.candidate = self.candidate_since_ns = None
        return self.state


def select_detection(boxes: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Choose the largest vehicle detection; target selection is not tracking."""
    return max(boxes, key=lambda row: row["bbox_area"], default=None)


def parse_yolo_boxes(xyxy_values, confidence_values, class_values, width: int, height: int) -> list[dict[str, Any]]:
    boxes=[]
    for xyxy, confidence, class_id in zip(xyxy_values, confidence_values, class_values):
        x1,y1,x2,y2=(float(value) for value in xyxy); class_id=int(class_id)
        if class_id not in VEHICLE_CLASS_IDS: continue
        boxes.append({"class_id":class_id,"class_name":VEHICLE_CLASS_NAMES[class_id],"confidence":float(confidence),
                      "bbox_x1":x1,"bbox_y1":y1,"bbox_x2":x2,"bbox_y2":y2,
                      "bbox_center_x":(x1+x2)/(2*width),"bbox_center_y":(y1+y2)/(2*height),
                      "bbox_width":(x2-x1)/width,"bbox_height":(y2-y1)/height,
                      "bbox_area":(x2-x1)*(y2-y1)/(width*height)})
    return boxes


def track_continuity(track_ids: list[int | None]) -> dict[str, int]:
    visible=[value for value in track_ids if value is not None]
    switches=sum(left!=right for left,right in zip(visible,visible[1:]))
    gaps=[]; current=0
    for value in track_ids:
        if value is None: current+=1
        elif current: gaps.append(current); current=0
    if current: gaps.append(current)
    return {"visible_frames":len(visible),"unique_track_ids":len(set(visible)),"track_switches":switches,
            "maximum_missing_run":max(gaps,default=0)}


def lidar_slice_action(predicted_state: str) -> str:
    if predicted_state=="NO_VEHICLE": return "EXCLUDE"
    if predicted_state=="MOVING": return "ACCEPT"
    if predicted_state=="STOPPED": return "FREEZE"
    return "UNKNOWN"


def summarize_lidar_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {"total_profiles":len(rows),"excluded_profiles":sum(row["slice_action"]=="EXCLUDE" for row in rows),
            "accepted_profiles":sum(row["slice_action"]=="ACCEPT" for row in rows),
            "frozen_profiles":sum(row["slice_action"]=="FREEZE" for row in rows),
            "unknown_profiles":sum(row["slice_action"]=="UNKNOWN" for row in rows),
            "moving_profiles_incorrectly_frozen":sum(row["ground_truth_state"]=="MOVING" and row["slice_action"]=="FREEZE" for row in rows),
            "stationary_profiles_incorrectly_accepted":sum(row["ground_truth_state"]=="STOPPED" and row["slice_action"]=="ACCEPT" for row in rows)}


def annotate_sample(source: Path, destination: Path, detection: dict[str, Any] | None, label: str) -> None:
    image = cv2.imread(str(source))
    if detection:
        x1, y1, x2, y2 = (round(detection[key]) for key in ("bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2"))
        cv2.rectangle(image, (x1, y1), (x2, y2), (0, 220, 0), 3)
        label += f" {detection['class_name']} {detection['confidence']:.3f}"
    cv2.putText(image, label, (20, 45), cv2.FONT_HERSHEY_SIMPLEX, .8, (0, 0, 255), 2)
    cv2.imwrite(str(destination), image)


def draw_plot(path: Path, rows: list[dict[str, Any]], markers: dict[str, int]) -> None:
    image = np.full((650, 1500, 3), 255, np.uint8)
    if not rows: return
    first, last = rows[0]["timestamp_ns"], rows[-1]["timestamp_ns"]; span=max(last-first,1)
    xof=lambda t: 60+round((t-first)/span*1380)
    for a,b in zip(rows,rows[1:]):
        y1=560-round(float(a.get("confidence") or 0)*450); y2=560-round(float(b.get("confidence") or 0)*450)
        cv2.line(image,(xof(a["timestamp_ns"]),y1),(xof(b["timestamp_ns"]),y2),(200,80,20),2)
    cv2.line(image,(60,560-round(WORKING_CONFIDENCE*450)),(1440,560-round(WORKING_CONFIDENCE*450)),(0,0,200),1)
    for label,timestamp in markers.items():
        x=xof(timestamp); cv2.line(image,(x,50),(x,580),(0,130,0),2); cv2.putText(image,label,(x+4,75),0,.45,(0,100,0),1)
    cv2.putText(image,"selected vehicle detection confidence; red line=0.25",(60,620),0,.6,(0,0,0),1)
    cv2.imwrite(str(path),image)


def audit(session: Path, scenario: str, model_path: Path, global_output: Path) -> dict[str, Any]:
    from ultralytics import YOLO

    output = session / "vehicle_tracking"; output.mkdir(parents=True, exist_ok=True)
    frames = load_frame_rows(session, verify_hashes=True)
    markers, issues = parse_ground_truth(session / "markers.jsonl", scenario)
    model = YOLO(str(model_path))
    rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    batch_size = 16
    for offset in range(0, len(frames), batch_size):
        batch = frames[offset:offset+batch_size]
        results = model.predict([row["path"] for row in batch], classes=list(VEHICLE_CLASS_IDS),
                                conf=AUDIT_CONFIDENCE, imgsz=INPUT_SIZE, device="cpu", verbose=False)
        for frame, result in zip(batch, results):
            height, width = result.orig_shape
            boxes=parse_yolo_boxes(result.boxes.xyxy.cpu().numpy(),result.boxes.conf.cpu().numpy(),
                                    result.boxes.cls.cpu().numpy(),width,height)
            selected=select_detection(boxes); timestamp=int(frame["captured_monotonic_ns"])
            ground="UNKNOWN" if issues else truth_at(timestamp,scenario,markers)
            rows.append({"session_key":session.name,"frame_index":offset+len(rows)-offset,
                         "timestamp_ns":timestamp,"file":Path(frame["path"]).name,"ground_truth_state":ground,
                         "vehicle_present_ground_truth":ground in {"MOVING","STOPPED"},
                         "detection_count":len(boxes),"detected":selected is not None,
                         "detected_at_025":bool(selected and selected["confidence"]>=WORKING_CONFIDENCE),
                         "inference_ms":float(result.speed.get("inference",0)), **(selected or {})})
    elapsed=time.perf_counter()-started
    active=[row for row in rows if row["vehicle_present_ground_truth"]]
    outside=[row for row in rows if row["ground_truth_state"]=="NO_VEHICLE"]
    detected=[row for row in active if row["detected_at_025"]]
    confidence=[row["confidence"] for row in active if row.get("confidence") is not None]
    detection_rate=len(detected)/len(active) if active else None
    all_confidence=[row["confidence"] for row in rows if row.get("confidence") is not None]
    tracking_allowed=detection_rate is not None and detection_rate>=MINIMUM_DETECTION_RATE_FOR_TRACKING
    summary={"session_key":session.name,"scenario":scenario,"ground_truth_status":"INCOMPLETE" if issues else "COMPLETE",
             "ground_truth_issues":issues,"model":{"name":MODEL_NAME,"ultralytics":"8.4.117","classes":VEHICLE_CLASS_NAMES,
             "audit_confidence":AUDIT_CONFIDENCE,"working_confidence":WORKING_CONFIDENCE,"input_size":INPUT_SIZE,"device":"CPU"},
             "frames_total":len(rows),"vehicle_present_frames":len(active),"detected_vehicle_frames_at_025":len(detected),
             "all_frames_with_vehicle_detection_at_010":sum(row["detected"] for row in rows),
             "all_frames_with_vehicle_detection_at_025":sum(row["detected_at_025"] for row in rows),
             "all_frame_confidence":{"count":len(all_confidence),"median":float(np.median(all_confidence)) if all_confidence else None,
             "p10":float(np.percentile(all_confidence,10)) if all_confidence else None,"p90":float(np.percentile(all_confidence,90)) if all_confidence else None},
             "detection_rate_at_025":detection_rate,"detections_at_010":sum(row["detected"] for row in active),
             "confidence":{"count":len(confidence),"median":float(np.median(confidence)) if confidence else None,
             "p10":float(np.percentile(confidence,10)) if confidence else None,"p90":float(np.percentile(confidence,90)) if confidence else None},
             "frames_without_detection":sum(not row["detected_at_025"] for row in active),
             "false_detection_frames_outside_vehicle_interval":sum(row["detected_at_025"] for row in outside),
             "inference_ms":{"median":float(np.median([row["inference_ms"] for row in rows])),"p90":float(np.percentile([row["inference_ms"] for row in rows],90))},
             "wall_clock_fps":len(rows)/elapsed,"tracking":{"status":"ELIGIBLE" if tracking_allowed else "SKIPPED_DETECTOR_RECALL_TOO_LOW",
             "minimum_detection_rate":MINIMUM_DETECTION_RATE_FOR_TRACKING,"bytetrack_run":False,"botsort_run":False},
             "result":"DETECTION_AUDIT_SUFFICIENT_FOR_TRACKING" if tracking_allowed else "YOLO_DETECTION_NOT_SUITABLE"}
    write_csv(output/"detections.csv",rows); write_csv(output/"tracks.csv",[]); write_csv(output/"motion_states.csv",[])
    profiles=read_jsonl(session/"lidar"/"raw_scans.jsonl"); lidar=[]
    for index,profile in enumerate(profiles):
        timestamp=int(profile["captured_monotonic_ns"]); ground="UNKNOWN" if issues else truth_at(timestamp,scenario,markers)
        predicted="NO_VEHICLE" if ground=="NO_VEHICLE" else "TRACK_LOST"
        lidar.append({"profile_index":index,"timestamp":timestamp,"ground_truth_state":ground,"predicted_state":predicted,
                      "slice_action":lidar_slice_action(predicted)})
    write_csv(output/"lidar_slice_simulation.csv",lidar); draw_plot(output/"tracking_plot.png",rows,markers)
    summary["lidar_slice_simulation"]=summarize_lidar_rows(lidar)
    (output/"tracking_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    global_output.mkdir(parents=True,exist_ok=True)
    global_csv=global_output/"detections.csv"; retained=[]
    if global_csv.is_file():
        with global_csv.open(encoding="utf-8",newline="") as handle:
            retained=[row for row in csv.DictReader(handle) if row.get("session_key")!=session.name]
    write_csv(global_csv,retained+rows)
    global_summary_path=global_output/"detection_summary.json"; sessions={}
    if global_summary_path.is_file():
        previous=json.loads(global_summary_path.read_text(encoding="utf-8"))
        sessions=previous.get("sessions",{})
    sessions[session.name]=summary
    aggregate={"sessions":sessions,"conclusion":"YOLO_DETECTION_NOT_SUITABLE" if any(
        item["result"]=="YOLO_DETECTION_NOT_SUITABLE" for item in sessions.values()) else "DETECTION_AUDIT_SUFFICIENT_FOR_TRACKING"}
    global_summary_path.write_text(json.dumps(aggregate,ensure_ascii=False,indent=2),encoding="utf-8")
    good=max((row for row in active if row.get("confidence") is not None),key=lambda row:row["confidence"],default=None)
    low=min((row for row in active if row.get("confidence") is not None),key=lambda row:row["confidence"],default=None)
    missed_candidates=[row for row in active if not row["detected_at_025"]]
    missed_target=(markers.get("STOPPED",markers.get("VEHICLE_ENTERED",0))+
                   markers.get("RESUMED",markers.get("VEHICLE_EXITED",0)))//2
    missed=min(missed_candidates,key=lambda row:abs(row["timestamp_ns"]-missed_target),default=None)
    false=next((row for row in outside if row["detected_at_025"]),None)
    if good: annotate_sample(session/"camera"/good["file"],global_output/"sample_good.jpg",good,"GOOD")
    if low: annotate_sample(session/"camera"/low["file"],global_output/"sample_low_confidence.jpg",low,"LOW CONF")
    if missed: annotate_sample(session/"camera"/missed["file"],global_output/"sample_missed.jpg",None,"MISSED vehicle")
    if false: annotate_sample(session/"camera"/false["file"],global_output/"sample_false_positive.jpg",false,"FALSE POSITIVE")
    return summary


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("session",type=Path)
    parser.add_argument("--scenario",required=True,choices=("stop-resume","no-stop")); parser.add_argument("--model",type=Path)
    parser.add_argument("--global-output",type=Path); args=parser.parse_args()
    session=args.session.resolve(); root=session.parent
    model=(args.model or root/"vehicle_tracking_research"/"models"/MODEL_NAME).resolve()
    global_output=(args.global_output or root/"vehicle_tracking_research").resolve()
    print(json.dumps(audit(session,args.scenario,model,global_output),ensure_ascii=False,indent=2))


if __name__=="__main__": main()
