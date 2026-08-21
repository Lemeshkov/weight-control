import json,time
from pathlib import Path
from services.side_camera_service import SideCameraService,parse_rtsp_url
from services.side_camera_experiment_recorder import SideCameraExperimentRecorder

class FakeClient:
 def __init__(self,**kwargs):self.kwargs=kwargs;self.is_connected=False;self.rtsp_reconnect_count=0;self.listeners=[];self.stopped=False
 def add_frame_listener(self,fn):self.listeners.append(fn)
 def connect(self):self.is_connected=True;return True
 def disconnect(self):self.is_connected=False;self.stopped=True
 def emit(self,sample):
  for fn in self.listeners:fn(sample)
class FailingClient(FakeClient):
 def connect(self):return False
def sample(seq,ns,jpeg=b'jpg'):
 return {'sequence_number':seq,'captured_monotonic_ns':ns,'camera_frame_read_completed_monotonic_ns':ns,'jpeg':jpeg,'width':1920,'height':1080}
def test_side_disabled_starts_without_url():
 s=SideCameraService(enabled=False,rtsp_url='',client_factory=FakeClient);assert s.start() and s.client is None
def test_missing_url_does_not_matter_when_disabled():assert SideCameraService(enabled=False,rtsp_url='').status()['enabled'] is False
def test_connection_failure_is_isolated():
 s=SideCameraService(enabled=True,rtsp_url='rtsp://u:p@127.0.0.1/x',client_factory=FailingClient);assert not s.start() and s.status()['connected'] is False
def test_reconnect_state_serialized():
 s=SideCameraService(enabled=True,rtsp_url='rtsp://u:p@127.0.0.1/x',client_factory=FakeClient);assert s.start();s.client.rtsp_reconnect_count=2;assert s.status()['reconnect_count']==2
def test_stale_detection():
 s=SideCameraService(enabled=True,rtsp_url='rtsp://u:p@127.0.0.1/x',stale_ms=1,client_factory=FakeClient);s.start();s._on_frame(sample(1,time.monotonic_ns()-2_000_000));assert s.status()['stale']
def test_frame_gap_detection():
 s=SideCameraService(enabled=True,rtsp_url='rtsp://u:p@127.0.0.1/x',gap_ms=100,client_factory=FakeClient);s.start();s._on_frame(sample(1,1_000_000_000));s._on_frame(sample(2,1_250_000_000));assert s.status()['frame_gap_count']==1 and s.status()['last_frame_gap_ms']==250
def test_status_contains_no_credentials():
 s=SideCameraService(enabled=True,rtsp_url='rtsp://secret:password@127.0.0.1/x',client_factory=FakeClient);s.start();encoded=json.dumps(s.status());assert 'secret' not in encoded and 'password' not in encoded
def test_rtsp_url_parser_decodes_credentials():assert parse_rtsp_url('rtsp://a%40b:p%3Ax@host:554/path')['username']=='a@b'
def test_experiment_lifecycle_and_files(tmp_path):
 r=SideCameraExperimentRecorder(base_dir=tmp_path,max_fps=1000);eid=r.start({'enabled':True,'transport_requested':'tcp','resolution':'1920x1080'},{'safe':'value'});r.record_side_frame({**sample(1,time.monotonic_ns()),'receive_monotonic_ns':time.monotonic_ns(),'receive_wall_ns':time.time_ns(),'frame_counter':1,'frame_gap_detected':False,'frame_gap_ms':None});r.record_lidar({'captured_monotonic_ns':time.monotonic_ns(),'ranges_mm':[1,2]});assert r.stop();d=tmp_path/eid;assert (d/'metadata.json').exists() and (d/'side_frames.jsonl').exists() and (d/'lidar_profiles.jsonl').exists() and len(list((d/'frames').glob('*.jpg')))==1
def test_metadata_has_no_rtsp_url(tmp_path):
 r=SideCameraExperimentRecorder(base_dir=tmp_path);eid=r.start({'enabled':True,'transport_requested':'tcp','resolution':None},{'camera_side_transport':'tcp'});r.stop();text=(tmp_path/eid/'metadata.json').read_text();assert 'rtsp://' not in text
def test_recorder_status_and_duplicate_start(tmp_path):
 r=SideCameraExperimentRecorder(base_dir=tmp_path);assert r.start({'enabled':False}) and r.start({'enabled':False}) is None and r.status()['active'];r.stop();assert not r.status()['active']
def test_recorder_stop_when_inactive(tmp_path):assert SideCameraExperimentRecorder(base_dir=tmp_path).stop() is False
def test_shutdown_stops_side_reader():
 s=SideCameraService(enabled=True,rtsp_url='rtsp://u:p@127.0.0.1/x',client_factory=FakeClient);s.start();client=s.client;s.stop();assert client.stopped
