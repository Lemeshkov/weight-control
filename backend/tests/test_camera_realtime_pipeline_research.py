import importlib.util,sys,builtins,json
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
def test_missing_matplotlib_does_not_lose_live_artifacts(tmp_path,monkeypatch):
 original=builtins.__import__
 def blocked(name,*args,**kwargs):
  if name.startswith('matplotlib'):raise ImportError('blocked for research test')
  return original(name,*args,**kwargs)
 monkeypatch.setattr(builtins,'__import__',blocked)
 timing=[{'frame_sequence':1,'monotonic_receive_time_ns':1,'wall_clock_receive_time':'x','decode_complete_time_ns':1,'time_since_previous_frame_ms':1.0,'reader_loop_duration_ms':1.0,'frontend_delivery_time_ns':'NOT_OBSERVED','pts_dts':'NOT_AVAILABLE'}]
 events=[{'event':'TEST'}];arch={'dedicated_reader_thread':True,'shared_latest_frame_slot':True,'unbounded_application_queue':False,'listeners_inline_reader':True,'capture_open_count_design':1,'frontend_reader_is_rtsp_reader':False};live={'backend':'FFMPEG','tcp':'TCP_REQUESTED_NOT_CONFIRMED','buffer_set':True}
 M.save_raw_artifacts(tmp_path,timing,events,[],arch,live,matplotlib_available=False,plots_created=False,plot_skip_reason='not_attempted_yet')
 created,reason=M.create_plots(tmp_path,timing);M.save_raw_artifacts(tmp_path,timing,events,[],arch,live,matplotlib_available=False,plots_created=created,plot_skip_reason=reason)
 for name in ('research_summary.json','camera_timing.csv','camera_latency_events.csv','h264_error_inventory.csv'):assert (tmp_path/name).exists()
 assert json.loads((tmp_path/'research_summary.json').read_text())['plot_skip_reason']=='matplotlib_not_installed'
