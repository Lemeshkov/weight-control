import asyncio,cv2,numpy as np
from services.development_shadow_producers import CameraLifecycleShadowProducer,LidarStrongMovementShadowProducer,ENTER_FRAMES,EXIT_FRAMES
from services.development_motion_provider import CameraEvidence,CameraState,DevelopmentMotionProvider
from services.lidar_profile_buffer import LidarProfileBuffer
def jpg(im):return cv2.imencode('.jpg',im)[1].tobytes()
def life():
 p=CameraLifecycleShadowProducer();bg=np.zeros((180,320),np.uint8)
 for i in range(5):p.process(jpg(bg),i)
 return p,bg
def vehicle(bg):im=bg.copy();im[20:170,70:260]=180;return im
def profile(t,value=1000):
 a=[value]*381;return {"captured_monotonic_ns":t,"start_angle_deg":-5.,"angular_step_deg":.5,"beam_count":381,"ranges_mm":a}
def test_presence_persistence_enter():
 p,b=life();rows=[p.process(jpg(vehicle(b)),10+i) for i in range(ENTER_FRAMES)];assert rows[-1]['transition']=='ENTER'
def test_single_false_detection_no_enter():
 p,b=life();assert p.process(jpg(vehicle(b)),10)['transition']=='NONE';assert not p.present
def test_temporary_miss_no_exit():
 p,b=life();[p.process(jpg(vehicle(b)),10+i) for i in range(ENTER_FRAMES)];assert p.process(jpg(b),20)['transition']=='NONE'
def test_sustained_absence_exit():
 p,b=life();[p.process(jpg(vehicle(b)),10+i) for i in range(ENTER_FRAMES)];rows=[p.process(jpg(b),20+i) for i in range(EXIT_FRAMES)];assert rows[-1]['transition']=='EXIT'
def test_lifecycle_independent_of_weight():
 p,b=life();assert 'weight' not in p.process(jpg(vehicle(b)),10)
def test_empty_vehicle_is_presence():
 p,b=life();empty=vehicle(b);empty[50:140,90:240]=0;rows=[p.process(jpg(empty),10+i) for i in range(ENTER_FRAMES)];assert rows[-1]['transition']=='ENTER'
def test_full_profile_listener_receives_beam_alignment():
 class C:
  is_connected=True;MIN_VALID_DISTANCE=100;MAX_VALID_DISTANCE=3000
  def get_scan_data(self):return 'raw'
  def parse_raw_data(self,x):return [100]*381
  def parse_diagnostic_scan(self,x):return {"start_angle_deg":-5.,"angular_step_deg":.5,"beam_count":381,"ranges_mm":[100]*381}
  def filter_angle(self,x,a):return x
  def filter_valid_distances(self,x):return x
 c=C();buf=LidarProfileBuffer(client=c);seen=[];buf.add_full_profile_listener(seen.append);asyncio.run(buf.capture_once());assert seen[0]['beam_count']==len(seen[0]['ranges_mm'])==381
def test_listener_exception_does_not_break_acquisition():
 class C:
  is_connected=True;MIN_VALID_DISTANCE=100;MAX_VALID_DISTANCE=3000
  def get_scan_data(self):return 'raw'
  def parse_raw_data(self,x):return [100]*381
  def parse_diagnostic_scan(self,x):return {"start_angle_deg":-5.,"angular_step_deg":.5,"beam_count":381,"ranges_mm":[100]*381}
  def filter_angle(self,x,a):return x
  def filter_valid_distances(self,x):return x
 buf=LidarProfileBuffer(client=C());buf.add_full_profile_listener(lambda x:(_ for _ in ()).throw(RuntimeError()));assert asyncio.run(buf.capture_once()) is not None
def test_strong_lidar_predicate_is_causal():
 p=LidarStrongMovementShadowProducer();p.process(profile(0));r=p.process(profile(1_000_000_000,1600));assert r['strong_sample'] and r['captured_monotonic_ns']==1_000_000_000
def test_single_strong_no_movement():
 p=LidarStrongMovementShadowProducer();p.process(profile(0));assert not p.process(profile(1_000_000_000,1600))['strong_movement']
def test_two_consecutive_strong_move():
 p=LidarStrongMovementShadowProducer();p.process(profile(0));p.process(profile(1_000_000_000,1600));assert p.process(profile(2_000_000_000,1700))['strong_movement']
def test_lidar_gap_unknown():
 p=LidarStrongMovementShadowProducer();p.process(profile(0));assert p.process(profile(2_000_000_000))['unknown_reason']=='SENSOR_GAP'
def test_lidar_resets_stop_candidate():
 p=DevelopmentMotionProvider();p.enter(0);p.update(CameraEvidence(0,CameraState.STATIONARY));p.update(CameraEvidence(1,CameraState.UNKNOWN),lidar_strong=True);assert p.stationary_since is None
def test_lidar_leaves_stopped():
 p=DevelopmentMotionProvider();p.enter(0);p.update(CameraEvidence(0,CameraState.STATIONARY));p.update(CameraEvidence(3_000_000_000,CameraState.STATIONARY));p.update(CameraEvidence(4_000_000_000,CameraState.UNKNOWN),lidar_strong=True);assert p.update(CameraEvidence(4_300_000_000,CameraState.UNKNOWN),lidar_strong=True)['development_state']=='VEHICLE_PRESENT_MOVING'
def test_camera_enter_starts_provider():p=DevelopmentMotionProvider();assert p.enter(1)['development_state']=='VEHICLE_PRESENT_MOVING'
def test_camera_exit_completes_provider():p=DevelopmentMotionProvider();p.enter(1);assert p.exit(2)['development_state']=='SESSION_COMPLETE'
def test_disabled_producer_has_no_runtime_callback():
 from services.development_motion_shadow import DevelopmentMotionShadow
 s=DevelopmentMotionShadow(False);s.on_full_lidar_profile({});assert not s._lidar_pending;s.shutdown()
def test_production_action_false():assert DevelopmentMotionProvider().snapshot(0)['production_action_triggered'] is False
def test_no_database_dependency():
 import services.development_shadow_producers as m;assert 'database' not in m.__dict__
def test_no_future_leakage_lidar_history():
 p=LidarStrongMovementShadowProducer();p.process(profile(10));assert all(x['captured_monotonic_ns']<=10 for x in p.history)
