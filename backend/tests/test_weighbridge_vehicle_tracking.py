from scripts.research_weighbridge_vehicle_tracking import (
    FrozenTrackingCandidate, MotionHysteresis, add_features, continuity, dominant_axis, interval_continuity, lidar_simulation
)


def row(t,x=None,y=None,track=1):
    visible=x is not None
    return {"timestamp_ns":t,"visible":visible,"track_id":track if visible else None,"bbox_center_x":x,"bbox_center_y":y,
        "bbox_x1":x-.1 if visible else None,"bbox_y1":y-.1 if visible else None,"bbox_x2":x+.1 if visible else None,
        "bbox_y2":y+.1 if visible else None,"bbox_area":.04 if visible else None}


def test_track_continuity_and_short_gap():
    assert continuity([1,1,None,1,2])["maximum_missing_run"]==1
    assert continuity([1,1,None,1,2])["track_switches"]==1
    rows=[{"timestamp_ns":1,"track_id":9},{"timestamp_ns":2,"track_id":None},{"timestamp_ns":3,"track_id":9}]
    assert interval_continuity(rows,1,4)["visibility_fraction"]==2/3


def test_dominant_axis_and_projected_velocity():
    axis=dominant_axis([(0,0),(1,2),(2,4)])
    assert axis[0]>0 and axis[1]>0
    rows,_=add_features([row(0,.1,.1),row(1_000_000_000,.2,.3)])
    assert rows[1]["projected_velocity"]>0


def test_hysteresis_stop_resume_and_no_vehicle_not_stopped():
    c=FrozenTrackingCandidate(stop_confirmation_ms=1000,resume_confirmation_ms=500)
    f=MotionHysteresis(c)
    assert f.update(0,False,None)[0]=="NO_VEHICLE"
    assert f.update(1,True,.1)[0]=="MOVING"
    assert f.update(100_000_000,True,0)[1]=="STOP_CANDIDATE"
    assert f.update(1_200_000_000,True,0)[0]=="STOPPED"
    assert f.update(1_300_000_000,False,None,1)[0]=="TRACK_LOST"
    assert f.update(1_400_000_000,True,.1)[0]=="MOVING"


def test_no_stop_scenario_has_no_false_stop():
    c=FrozenTrackingCandidate(stop_confirmation_ms=500,rolling_window=1)
    rows=[row(i*250_000_000,.1+i*.03,.2+i*.02) for i in range(12)]
    result,_=add_features(rows,c)
    assert all(r["predicted_state"]!="STOPPED" for r in result)


def test_stop_resume_scenario_transitions():
    c=FrozenTrackingCandidate(stop_threshold_per_sec=.01,start_threshold_per_sec=.03,rolling_window=1,stop_confirmation_ms=400,resume_confirmation_ms=300)
    positions=[.1,.15,.2,.2,.2,.2,.25,.3,.35]
    result,_=add_features([row(i*250_000_000,x,.5) for i,x in enumerate(positions)],c)
    states=[r["predicted_state"] for r in result]
    assert "STOPPED" in states and states[-1]=="MOVING"


def test_lidar_slice_simulation_mapping(tmp_path):
    (tmp_path/'lidar').mkdir();(tmp_path/'lidar'/'raw_scans.jsonl').write_text('{"captured_monotonic_ns":2}\n',encoding='utf-8')
    timeline=[{"timestamp_ns":1,"predicted_state":"STOPPED"}]
    rows,summary=lidar_simulation(tmp_path,timeline,'no-stop',{})
    assert rows[0]["slice_action"]=="FREEZE" and summary["frozen_profiles"]==1
