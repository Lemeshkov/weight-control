import csv,json,time
from services.side_camera_session_recorder import SideCameraSessionRecorder,redact_stream_url
from scripts.analyze_side_camera_capture import analyze

def frame(seq,ns):return {'sequence_number':seq,'frame_counter':seq,'captured_monotonic_ns':ns,'receive_monotonic_ns':ns,'receive_wall_ns':time.time_ns(),'jpeg':b'jpeg','width':640,'height':480}

def test_disabled_and_not_configured_are_isolated(tmp_path):
 assert not SideCameraSessionRecorder(enabled=False,configured=True,base_dir=tmp_path).start('s')
 assert not SideCameraSessionRecorder(enabled=True,configured=False,base_dir=tmp_path).start('s')
 assert not tmp_path.joinpath('s').exists()

def test_mock_capture_same_session_monotonic_manifest_and_no_credentials(tmp_path):
 r=SideCameraSessionRecorder(enabled=True,configured=True,base_dir=tmp_path,target_fps=15,pre_trigger_seconds=1)
 r.record_frame(frame(1,1_000_000_000));assert r.start('main-session')
 r.record_frame(frame(2,1_066_000_000));r.record_frame(frame(2,1_066_000_000));r.record_frame(frame(3,1_133_000_000));assert r.stop()
 root=tmp_path/'main-session'/'camera_side';assert len(list((root/'frames').glob('*.jpg')))==3
 with (root/'frames.csv').open(newline='',encoding='utf-8') as f:rows=list(csv.DictReader(f))
 assert [int(x['captured_monotonic_ns']) for x in rows]==[1_000_000_000,1_066_000_000,1_133_000_000]
 manifest=json.loads((root/'manifest.json').read_text());text=json.dumps(manifest).lower();assert manifest['capture_status']=='COMPLETED' and not manifest['credentials_stored'];assert 'password' not in text

def test_capture_analyzer_and_lidar_nearest_distance(tmp_path):
 r=SideCameraSessionRecorder(enabled=True,configured=True,base_dir=tmp_path,pre_trigger_seconds=0)
 assert r.start('s')
 for i,ns in enumerate((1_000_000_000,1_100_000_000,1_200_000_000),1):r.record_frame(frame(i,ns))
 r.stop();lidar=tmp_path/'s'/'lidar';lidar.mkdir();(lidar/'raw_scans.jsonl').write_text('\n'.join(json.dumps({'captured_monotonic_ns':x}) for x in (1_040_000_000,1_160_000_000)))
 result=analyze('s',tmp_path);assert result['frame_count']==3 and result['timestamp_monotonicity'];assert result['duplicate_timestamp_count']==0 and result['max_abs_time_difference_ms']==40

def test_redaction_removes_credentials():
 value=redact_stream_url('rtsp://user:password@10.79.24.188:554/verified')
 assert value=='rtsp://10.79.24.188:554/verified' and 'password' not in value
