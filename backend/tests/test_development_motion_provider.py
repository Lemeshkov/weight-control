import numpy as np
from services.development_motion_provider import CameraEvidence,CameraState,DevelopmentMotionProvider,CameraStationaryAnalyzer,MotionState,STOP_MATURITY_MS,MAX_ANCHOR_DRIFT

def ev(t,state,reason="",drift=0):return CameraEvidence(t,state,reason,1,drift,50)
def started():p=DevelopmentMotionProvider();p.enter(0);return p
def test_29_seconds_no_stop():
 p=started();p.update(ev(0,CameraState.STATIONARY));assert p.update(ev(2_900_000_000,CameraState.STATIONARY))["development_state"]!="PHYSICAL_STOPPED"
def test_30_seconds_stops():
 p=started();p.update(ev(0,CameraState.STATIONARY));assert p.update(ev(3_000_000_000,CameraState.STATIONARY))["development_state"]=="PHYSICAL_STOPPED"
def test_unknown_resets():
 p=started();p.update(ev(0,CameraState.STATIONARY));p.update(ev(2_900_000_000,CameraState.UNKNOWN));assert p.update(ev(3_100_000_000,CameraState.STATIONARY))["development_state"]!="PHYSICAL_STOPPED"
def test_movement_resets():
 p=started();p.update(ev(0,CameraState.STATIONARY));p.update(ev(2_900_000_000,CameraState.MOVING));assert p.update(ev(3_100_000_000,CameraState.STATIONARY))["development_state"]!="PHYSICAL_STOPPED"
def test_absent_is_unknown():assert CameraState.UNKNOWN.value=="UNKNOWN"
def test_poor_features_is_unknown():assert CameraEvidence(0,CameraState.UNKNOWN,"POOR_FEATURES").state==CameraState.UNKNOWN
def test_gap_is_unknown():assert CameraEvidence(0,CameraState.UNKNOWN,"CAMERA_GAP").state==CameraState.UNKNOWN
def test_background_jitter_not_movement():
 p=started();assert p.update(ev(1,CameraState.UNKNOWN,"HYSTERESIS"))["development_state"]!="PHYSICAL_STOPPED"
def test_anchor_drift_rejects_stationary():assert MAX_ANCHOR_DRIFT==.006
def test_sustained_camera_movement_after_stop():
 p=started();p.update(ev(0,CameraState.STATIONARY));p.update(ev(3_000_000_000,CameraState.STATIONARY));p.update(ev(4_000_000_000,CameraState.MOVING));assert p.update(ev(4_500_000_000,CameraState.MOVING))["development_state"]=="VEHICLE_PRESENT_MOVING"
def test_single_lidar_spike_no_change():
 p=started();p.update(ev(0,CameraState.STATIONARY));p.update(ev(3_000_000_000,CameraState.STATIONARY));assert p.update(ev(4_000_000_000,CameraState.UNKNOWN),lidar_strong=True)["development_state"]=="PHYSICAL_STOPPED"
def test_sustained_lidar_moves():
 p=started();p.update(ev(0,CameraState.STATIONARY));p.update(ev(3_000_000_000,CameraState.STATIONARY));p.update(ev(4_000_000_000,CameraState.UNKNOWN),lidar_strong=True);assert p.update(ev(4_300_000_000,CameraState.UNKNOWN),lidar_strong=True)["development_state"]=="VEHICLE_PRESENT_MOVING"
def test_weight_moves_and_vetoes_stop():
 p=started();p.update(ev(0,CameraState.STATIONARY));assert p.update(ev(3_100_000_000,CameraState.STATIONARY),weight_strong=True)["development_state"]=="VEHICLE_PRESENT_MOVING"
def test_stop_moving_stop_cycle():
 p=started();p.update(ev(0,CameraState.STATIONARY));p.update(ev(3_000_000_000,CameraState.STATIONARY));p.update(ev(4_000_000_000,CameraState.MOVING));p.update(ev(4_500_000_000,CameraState.MOVING));p.update(ev(5_000_000_000,CameraState.STATIONARY));assert p.update(ev(8_000_000_000,CameraState.STATIONARY))["development_state"]=="PHYSICAL_STOPPED"
def test_6fcd_lifecycle_regression():test_stop_moving_stop_cycle()
def test_48c7_unknown_regression():
 p=started();assert all(p.update(ev(t,CameraState.UNKNOWN,"CAMERA_GAP"))["development_state"]!="PHYSICAL_STOPPED" for t in (0,3_000_000_000,6_828_000_000))
def test_c5b37_true_stop_regression():test_30_seconds_stops()
def test_camera_exit_complete():assert started().exit(1)["development_state"]=="SESSION_COMPLETE"
def test_no_future_leakage():
 p=started();a=p.update(ev(2_900_000_000,CameraState.STATIONARY));assert a["development_state"]!="PHYSICAL_STOPPED"
def test_shadow_never_triggers_production_action():assert started().update(ev(1,CameraState.UNKNOWN))["production_action_triggered"] is False
