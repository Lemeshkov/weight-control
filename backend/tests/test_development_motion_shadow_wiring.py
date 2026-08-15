from services.development_motion_provider import CameraEvidence,CameraState,DevelopmentMotionProvider
from services.development_motion_shadow import DevelopmentMotionShadow,StrongWeightMovementProvider,WEIGHT_STRONG_MOVEMENT_KG
def ev(t,s):return CameraEvidence(t,s,features=50)
def stopped():
 p=DevelopmentMotionProvider();p.enter(0);p.update(ev(0,CameraState.STATIONARY));p.update(ev(3_000_000_000,CameraState.STATIONARY));return p
def test_disabled_is_trivial_flag_check():
 s=DevelopmentMotionShadow(False);s._executor.submit=lambda *a:(_ for _ in ()).throw(AssertionError());s.on_camera_frame({});s.shutdown()
def test_camera_enter_creates_lifecycle():
 s=DevelopmentMotionShadow(True);s.camera_enter(1);assert s.provider.state.value=="VEHICLE_PRESENT_MOVING";s.shutdown()
def test_camera_exit_completes():
 s=DevelopmentMotionShadow(True);s.camera_enter(1);s.camera_exit(2);assert s.provider.state.value=="SESSION_COMPLETE";s.shutdown()
def test_three_seconds_stops():assert stopped().state.value=="PHYSICAL_STOPPED"
def test_unknown_resets_candidate():
 p=DevelopmentMotionProvider();p.enter(0);p.update(ev(0,CameraState.STATIONARY));p.update(ev(2_900_000_000,CameraState.UNKNOWN));assert p.stationary_since is None
def test_lidar_strong_vetoes_stop():
 p=DevelopmentMotionProvider();p.enter(0);p.update(ev(0,CameraState.STATIONARY),lidar_strong=True);assert p.update(ev(3_000_000_000,CameraState.STATIONARY),lidar_strong=True)["development_state"]=="VEHICLE_PRESENT_MOVING"
def test_one_lidar_spike_does_not_veto():
 p=stopped();assert p.update(ev(4_000_000_000,CameraState.UNKNOWN),lidar_strong=True)["development_state"]=="PHYSICAL_STOPPED"
def test_two_lidar_profiles_veto():
 p=stopped();p.update(ev(4_000_000_000,CameraState.UNKNOWN),lidar_strong=True);assert p.update(ev(4_300_000_000,CameraState.UNKNOWN),lidar_strong=True)["development_state"]=="VEHICLE_PRESENT_MOVING"
def test_weight_strong_immediate():
 p=StrongWeightMovementProvider();assert not p.update(0,1000);assert p.update(1,1000+WEIGHT_STRONG_MOVEMENT_KG)
def test_stale_weight_not_used():
 p=StrongWeightMovementProvider();p.update(0,0);p.update(1,1000);assert p.at(2_000_000_000)[0] is False
def test_stopped_camera_movement_moves():
 p=stopped();p.update(ev(4_000_000_000,CameraState.MOVING));assert p.update(ev(4_500_000_000,CameraState.MOVING))["development_state"]=="VEHICLE_PRESENT_MOVING"
def test_stopped_lidar_movement_moves():test_two_lidar_profiles_veto()
def test_stopped_weight_movement_moves():
 p=stopped();assert p.update(ev(4_000_000_000,CameraState.UNKNOWN),weight_strong=True)["development_state"]=="VEHICLE_PRESENT_MOVING"
def test_stop_move_stop_cycle():
 p=stopped();p.update(ev(4_000_000_000,CameraState.MOVING));p.update(ev(4_500_000_000,CameraState.MOVING));p.update(ev(5_000_000_000,CameraState.STATIONARY));assert p.update(ev(8_000_000_000,CameraState.STATIONARY))["development_state"]=="PHYSICAL_STOPPED"
def test_shadow_exception_cannot_escape(monkeypatch):
 import services.development_motion_shadow as m
 class Recorder:
  active=True
  def status(self):return {"session_key":"x"}
  def record_event(self,*a,**k):pass
 monkeypatch.setattr(m,"diagnostic_recorder",Recorder());s=DevelopmentMotionShadow(True);s.provider.enter(0);s.analyzer.process=lambda *a:(_ for _ in ()).throw(RuntimeError());s._process({"captured_monotonic_ns":1,"jpeg":b""});assert s.provider.last_camera==CameraState.UNKNOWN;s.shutdown()
def test_queue_overflow_does_not_block():
 s=DevelopmentMotionShadow(True);s._pending=True;s.on_camera_frame({"captured_monotonic_ns":1});assert s._dropped_frames==1;s._pending=False;s.shutdown()
def test_production_action_always_false():assert stopped().snapshot(1)["production_action_triggered"] is False
