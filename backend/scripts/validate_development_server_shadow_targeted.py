"""Fast disclosed-only validation of DEVELOPMENT server-shadow producers."""
import csv,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.development_shadow_producers import CameraLifecycleShadowProducer,LidarStrongMovementShadowProducer
from services.development_motion_provider import CameraEvidence,CameraState,DevelopmentMotionProvider
from services.development_motion_shadow import StrongWeightMovementProvider

ROOT=Path("diagnostics");OUT=ROOT/"development_server_shadow_validation"
FOUR={
"0c2da0855bec496c8c7b49c47fcec5e5":["frame_01044886.jpg","frame_01045004.jpg","frame_01045375.jpg","frame_01045480.jpg"],
"48c7f5ddb6944d88bad0f389a804f323":["frame_01047440.jpg","frame_01047695.jpg","frame_01048086.jpg","frame_01048118.jpg"],
"47d81f2b8a3f4ccfa19ddfd8938d79f5":["frame_00937000.jpg","frame_00937176.jpg","frame_00938817.jpg","frame_00938985.jpg"],
"4edc4a680ee745d6a1363f29851031fc":["frame_00969922.jpg","frame_00970096.jpg","frame_00971983.jpg","frame_00972101.jpg"],
"be32452fab4e4249b2d7365a576a9beb":["frame_01109091.jpg","frame_01109236.jpg","frame_01110845.jpg","frame_01110989.jpg"],
"55b8629338cc4ce7b7db2546e520667b":["frame_01403152.jpg","frame_01403259.jpg","frame_01404367.jpg","frame_01404562.jpg"],
"c50b9bdde9244c56a4390a655c96eb04":["frame_01419633.jpg","frame_01419785.jpg","frame_01420912.jpg","frame_01421045.jpg"],
"ae4ff69e66c74b1aa631cba30c2e0983":["frame_01531546.jpg","frame_01531680.jpg","frame_01533048.jpg","frame_01533197.jpg"],
"3c099182103a410b9606107b26554941":["frame_02993737.jpg","frame_02993841.jpg","frame_02995850.jpg","frame_02995945.jpg"],
"e6cab68355ad48fb8467ced28bb0ce8c":["frame_03010872.jpg","frame_03010981.jpg","frame_03011230.jpg","frame_03011453.jpg"],
"6fcd75b17a7040788f7eb6cab41567ef":["frame_04000738.jpg","frame_04000842.jpg","frame_04002062.jpg","frame_04002165.jpg"]}
SIX={
"36968639548443bca68f68ba28495716":["frame_04097804.jpg","frame_04097888.jpg","frame_04098042.jpg","frame_04098483.jpg","frame_04098815.jpg","frame_04098919.jpg"],
"cabe49c7dd5c4aae8bb1800fdceddfed":["frame_04143847.jpg","frame_04143946.jpg","frame_04144228.jpg","frame_04145274.jpg","frame_04145743.jpg","frame_04145844.jpg"],
"9ae7c89c21b541aab2e445f929d79532":["frame_04205722.jpg","frame_04205887.jpg","frame_04206576.jpg","frame_04207987.jpg","frame_04208209.jpg","frame_04208322.jpg"]}
LIDAR=("48c7f5ddb6944d88bad0f389a804f323","55b8629338cc4ce7b7db2546e520667b","be32452fab4e4249b2d7365a576a9beb","42c2a07c97ae413b8d6b2545434e2216","8d4ede12003c4c748f3d436fbbc9c658","3df8876817b744fa8f9f97eccb9c0c8d","c50b9bdde9244c56a4390a655c96eb04","ae4ff69e66c74b1aa631cba30c2e0983")
E2E=("48c7f5ddb6944d88bad0f389a804f323","c5b37e30c42a4d8c8f007491eb96f2d7","6fcd75b17a7040788f7eb6cab41567ef","36968639548443bca68f68ba28495716","cabe49c7dd5c4aae8bb1800fdceddfed","9ae7c89c21b541aab2e445f929d79532","42c2a07c97ae413b8d6b2545434e2216","8d4ede12003c4c748f3d436fbbc9c658","3df8876817b744fa8f9f97eccb9c0c8d","55b8629338cc4ce7b7db2546e520667b")
def read(p):
 with p.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def write(name,rows):
 p=OUT/name
 if not rows:p.write_text("",encoding="utf-8");return
 fields=list(dict.fromkeys(k for r in rows for k in r))
 with p.open("w",encoding="utf-8",newline="") as f:w=csv.DictWriter(f,fields);w.writeheader();w.writerows(rows)
def refs():
 result=[]
 for s,frames in {**FOUR,**SIX}.items():
  by={r["file"]:int(r["captured_monotonic_ns"]) for r in read(ROOT/s/"camera"/"frames.csv")};names=("ENTER","STOPPED","RESUMED","EXIT") if len(frames)==4 else ("ENTER","STOPPED","DRIVER_EXITED","DRIVER_RETURNED","RESUMED","EXIT");m=dict(zip(names,frames))
  result.append({"session_id":s,"manual_enter_frame":m["ENTER"],"manual_enter_ns":by[m["ENTER"]],"manual_exit_frame":m["EXIT"],"manual_exit_ns":by[m["EXIT"]],"driver_exit_ns":by[m["DRIVER_EXITED"]] if "DRIVER_EXITED" in m else "","driver_return_ns":by[m["DRIVER_RETURNED"]] if "DRIVER_RETURNED" in m else "","resume_ns":by[m["RESUMED"]],"source":"existing disclosed research frame markers + frames.csv"})
 return result
def inventory(ref_by):
 sessions=read(ROOT/"fixed_3s_full_camera_replay"/"corpus_inventory.csv");rows=[]
 for x in sessions:
  s=x["session_id"];cam=ROOT/s/"camera"/"frames.csv"
  rows.append({"session_id":s,"camera_frames_available":cam.exists(),"camera_features_cached":(ROOT/"camera_feature_cache_v2"/s/"camera_features.csv").exists(),"camera_lifecycle_cached":False,"lidar_features_cached":any((ROOT/d/s).exists() for d in ("lidar_cross_section_progression_research","lidar_weight_positive_stationary_research","lidar_weight_post_holdout_adjudication_v3")),"weight_cached":(ROOT/s/"weight"/"snapshots.csv").exists(),"manual_enter_available":s in ref_by,"manual_exit_available":s in ref_by,"requires_raw_replay":s in ref_by})
 return rows
def camera_validation(ref):
 s=ref["session_id"];frames=read(ROOT/s/"camera"/"frames.csv");enter=int(ref["manual_enter_ns"]);exit=int(ref["manual_exit_ns"]);windows=[(enter-5_000_000_000,enter+5_000_000_000),(exit-8_000_000_000,exit+8_000_000_000)]
 if ref["driver_exit_ns"]:windows.extend([(int(ref["driver_exit_ns"])-5_000_000_000,int(ref["driver_exit_ns"])+5_000_000_000),(int(ref["driver_return_ns"])-5_000_000_000,int(ref["driver_return_ns"])+5_000_000_000)])
 selected=[r for r in frames if any(a<=int(r["captured_monotonic_ns"])<=b for a,b in windows)];p=CameraLifecycleShadowProducer();events=[];cpu=[]
 for r in selected:
  t=time.perf_counter_ns();z=p.process((ROOT/s/"camera"/r["file"]).read_bytes(),int(r["captured_monotonic_ns"]));cpu.append((time.perf_counter_ns()-t)/1e6)
  if z["transition"]!="NONE":events.append({**z,"frame":r["file"]})
 en=next((x for x in events if x["transition"]=="ENTER"),None);ex=next((x for x in events if x["transition"]=="EXIT" and x["captured_monotonic_ns"]>=exit-8_000_000_000),None);false_en=[x for x in events if x["transition"]=="ENTER" and en and x is not en and x["captured_monotonic_ns"]<exit];false_ex=[x for x in events if x["transition"]=="EXIT" and x["captured_monotonic_ns"]<exit-8_000_000_000];driver=[]
 if ref["driver_exit_ns"]:driver=[x for x in events if int(ref["driver_exit_ns"])<=x["captured_monotonic_ns"]<=int(ref["driver_return_ns"])]
 return {"session_id":s,"frames_decoded":len(selected),"enter_detected":en is not None,"enter_frame":"" if en is None else en["frame"],"enter_offset_ms":"" if en is None else (en["captured_monotonic_ns"]-enter)/1e6,"exit_detected":ex is not None,"exit_frame":"" if ex is None else ex["frame"],"exit_offset_ms":"" if ex is None else (ex["captured_monotonic_ns"]-exit)/1e6,"false_enter_count":len(false_en),"false_exit_count":len(false_ex),"driver_lifecycle_errors":len(driver),"transition_count":len(events),"cpu_ms_per_frame":sum(cpu)/len(cpu)}
def raw_profiles(s):
 with (ROOT/s/"lidar"/"raw_scans.jsonl").open(encoding="utf-8") as f:return [json.loads(x) for x in f]
def lidar_target(s,ref_by,event_refs):
 if s==LIDAR[0]:return 1106060718000000
 if s in ref_by:return int(ref_by[s]["resume_ns"])
 return int(event_refs[s]["resume_hint_ns"])
def lidar_validation(s,ref_by,event_refs):
 target=lidar_target(s,ref_by,event_refs);raw=[x for x in raw_profiles(s) if target-7_500_000_000<=int(x["captured_monotonic_ns"])<=target+5_000_000_000];p=LidarStrongMovementShadowProducer();rows=[];cpu=[]
 for x in raw:
  t=time.perf_counter_ns();z=p.process(x);cpu.append((time.perf_counter_ns()-t)/1e6);rows.append(z)
 confirmed=sum(bool(x["strong_movement"]) for x in rows);pending=sum(x["strong_sample"] and not x["strong_movement"] for x in rows);unknown=sum(bool(x["unknown_reason"]) for x in rows);comparisons=[];cached=ROOT/"lidar_cross_section_progression_research"/s/"zone_progression.csv"
 if cached.exists():
  by={(int(x["timestamp_ns"]),x["zone"]):float(x["progression_score"]) for x in read(cached) if x["progression_score"]}
  mature_after=int(raw[0]["captured_monotonic_ns"])+5_000_000_000 if raw else 0
  for x in rows:
   for zone,value in x["zone_evidence"].items():
    if x["captured_monotonic_ns"]>=mature_after and value is not None and (x["captured_monotonic_ns"],zone) in by:comparisons.append(abs(value-by[(x["captured_monotonic_ns"],zone)]))
 return {"session_id":s,"window_center_ns":target,"profiles":len(rows),"strong_samples":sum(x["strong_sample"] for x in rows),"confirmed_movement_profiles":confirmed,"single_pending_profiles":pending,"unknown_gap_profiles":unknown,"two_profile_persistence_observed":any(x["strong_count"]>=2 for x in rows),"48c7_protected":s!=LIDAR[0] or confirmed>0 or unknown>0,"cached_zone_values_compared":len(comparisons),"max_cached_score_abs_error":"" if not comparisons else max(comparisons),"cpu_ms_per_profile":sum(cpu)/len(cpu) if cpu else ""}
def truth(v):return str(v).lower()=="true"
def e2e(s):
 rows=read(ROOT/"camera_feature_cache_v2"/s/"camera_features.csv");p=DevelopmentMotionProvider();events=[p.enter(int(rows[0]["timestamp_ns"]))];previous=p.state.value;cpu=[]
 for r in rows:
  state=CameraState.MOVING if truth(r["movement_positive"]) else CameraState.STATIONARY if truth(r["stationary_positive"]) else CameraState.UNKNOWN;e=CameraEvidence(int(r["timestamp_ns"]),state,r.get("unknown_reason","") if state==CameraState.UNKNOWN else "",int(float(r["anchor_id"])) if r.get("anchor_id") else None,float(r["anchor_displacement"] or 0),int(float(r["features"] or 0)),float(r["cpu_ms"] or 0));t=time.perf_counter_ns();z=p.update(e);cpu.append((time.perf_counter_ns()-t)/1e6)
  if z["development_state"]!=previous:events.append(z);previous=z["development_state"]
 events.append(p.exit(int(rows[-1]["timestamp_ns"])+1));states=[x["development_state"] for x in events]
 return {"session_id":s,"cached_camera_events":len(rows),"enter":states[0]=="VEHICLE_PRESENT_MOVING","stop_candidate":"STOP_CANDIDATE" in states,"physical_stopped":"PHYSICAL_STOPPED" in states,"moving_after_stop":any(states[i]=="PHYSICAL_STOPPED" and states[i+1]=="VEHICLE_PRESENT_MOVING" for i in range(len(states)-1)),"exit_session_complete":states[-1]=="SESSION_COMPLETE","state_path":"->".join(states),"provider_cpu_ms_per_event":sum(cpu)/len(cpu),"production_action_triggered":any(x.get("production_action_triggered",False) for x in events)}
def main():
 OUT.mkdir(parents=True,exist_ok=True);references=refs();ref_by={x["session_id"]:x for x in references};write("manual_lifecycle_reference.csv",references);write("cache_inventory.csv",inventory(ref_by));camera=[camera_validation(x) for x in references];write("camera_lifecycle_validation.csv",camera)
 event_rows=read(ROOT/"lidar_weight_post_holdout_adjudication_v3"/"event_window_quality.csv");event_refs={x["session_id"]:x for x in event_rows};lidar=[lidar_validation(s,ref_by,event_refs) for s in LIDAR];write("lidar_targeted_validation.csv",lidar);end=[e2e(s) for s in E2E];write("end_to_end_targeted.csv",end)
 weight=StrongWeightMovementProvider();wt=[]
 for i,v in enumerate((10000.,10649.,10650.,10000.)):
  t=time.perf_counter_ns();weight.update(i*100_000_000,v);wt.append((time.perf_counter_ns()-t)/1e6)
 summary={"total_targeted_sessions":len(set(ref_by)|set(LIDAR)|set(E2E)),"camera_lifecycle_validated_sessions":len(camera),"lidar_validated_windows":len(lidar),"end_to_end_replay_sessions":len(end),"camera_enter_ready":all(x["enter_detected"] and x["false_enter_count"]==0 for x in camera),"camera_exit_ready":all(x["exit_detected"] and x["false_exit_count"]==0 for x in camera),"false_camera_enter":sum(x["false_enter_count"] for x in camera),"false_camera_exit":sum(x["false_exit_count"] for x in camera),"driver_induced_lifecycle_errors":sum(x["driver_lifecycle_errors"] for x in camera),"lidar_ready":all(x["profiles"]>0 and x["two_profile_persistence_observed"] for x in lidar),"48c7_protected":next(x["48c7_protected"] for x in lidar if x["session_id"]==LIDAR[0]),"single_lidar_spike_suppression":"UNIT_TESTED; targeted actual pending profiles="+str(sum(x["single_pending_profiles"] for x in lidar)),"known_movement_detected":sum(x["confirmed_movement_profiles"]>0 for x in lidar),"raw_camera_frames_decoded":sum(x["frames_decoded"] for x in camera),"end_to_end_session_complete":sum(x["exit_session_complete"] for x in end),"production_actions":sum(x["production_action_triggered"] for x in end),"performance":{"camera_lifecycle_cpu_ms_per_frame":sum(x["cpu_ms_per_frame"]*x["frames_decoded"] for x in camera)/sum(x["frames_decoded"] for x in camera),"camera_texture_cached_cpu_ms_per_frame":sum(float(r["cpu_ms"] or 0) for s in E2E for r in read(ROOT/"camera_feature_cache_v2"/s/"camera_features.csv"))/sum(len(read(ROOT/"camera_feature_cache_v2"/s/"camera_features.csv")) for s in E2E),"lidar_cpu_ms_per_profile":sum(float(x["cpu_ms_per_profile"]) for x in lidar)/len(lidar),"weight_cpu_ms_per_sample":sum(wt)/len(wt),"provider_cpu_ms_per_event":sum(x["provider_cpu_ms_per_event"] for x in end)/len(end)},"full_29119_replay":False,"threshold_tuning":False,"unseen_opened":False}
 (OUT/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8");print(json.dumps(summary,indent=2))
if __name__=="__main__":main()
