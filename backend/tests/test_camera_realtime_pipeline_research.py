import importlib.util,sys
from pathlib import Path
P=Path(__file__).parents[1]/'scripts/research_camera_realtime_pipeline.py';S=importlib.util.spec_from_file_location('camrt',P);M=importlib.util.module_from_spec(S);sys.modules[S.name]=M;S.loader.exec_module(M)
def test_latest_slot_replaces_not_queues():
 s=M.LatestFrameSlot();s.publish(M.Frame(1,1,''));s.publish(M.Frame(2,2,''));assert s.get().sequence==2 and s.replaced==1
def test_slow_consumer_has_bounded_age():
 r,_,_=M.fake_run(200,duration_s=1);assert max(x['frame_age_ms'] for x in r)<250
def test_slow_consumer_skips_frames():
 r,_,_=M.fake_run(500,duration_s=2);assert sum(x['consumer_skipped_since_last'] for x in r)>0
def test_no_consumer_queue_growth_contract():
 r,_,_=M.fake_run(1000,duration_s=2);assert len(r)<=3
def test_architecture_detects_latest_slot():
 a=M.audit_architecture(Path.cwd());assert a['dedicated_reader_thread'] and a['shared_latest_frame_slot'] and not a['unbounded_application_queue']
def test_frame_timestamp_is_receive_not_exposure_contract():assert M.Frame(1,2,'').receive_ns==2
