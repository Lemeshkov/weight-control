import importlib.util
from pathlib import Path
import numpy as np
BASE=Path(__file__).resolve().parents[1]/"scripts"
def load(name):
 spec=importlib.util.spec_from_file_location(name,BASE/f"{name}.py");module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
capture=load("capture_lidar_calibration");analysis=load("analyze_lidar_calibration_capture")
def parsed(raw=None):
 raw=raw or list(range(1,382));return {"start_angle_deg":-5.,"end_angle_deg":185.,"angular_step_deg":.5,"beam_count":381,"ranges_raw":raw,"scale_factor_raw":0x40000000,"scale_offset_raw":0}
def rows(values,count=5):return [{"ranges_physical_mm":list(values)} for _ in range(count)]
def test_raw_scale_factor_decoding():assert capture.decode_scale_factor(0x40000000)==2.
def test_preserves_full_381_beam_profile():assert len(capture.scan_record(parsed(),"x","empty_before",0,1,"t")["ranges_raw"])==381
def test_physical_range_conversion_before_production_filter():assert capture.scan_record(parsed(),"x","empty_before",0,1,"t")["ranges_physical_mm"][-1]==762.
def test_output_schema_and_no_production_action():
 r=capture.scan_record(parsed(),"x","marker",0,1,"t");assert {"capture_id","mode","ranges_physical_mm","valid_mask_raw"}<=r.keys();assert r["production_action_triggered"] is False
def test_invalid_beam_is_null_and_topology_preserved():
 r=capture.scan_record(parsed([1,0,-1]+[2]*378),"x","empty",0,1,"t");assert r["ranges_physical_mm"][:3]==[2.,None,None];assert len(r["valid_mask_raw"])==381
def test_empty_before_after_comparison_identical():assert analysis.compare_empty(rows(np.arange(381)),rows(np.arange(381)))["p99_delta_mm"]==0
def test_marker_difference_detects_coherent_region():
 empty=np.full(381,5000.);marker=empty.copy();marker[100:105]-=500;*_,region=analysis.marker_difference(rows(empty),rows(marker));assert list(region)==list(range(100,105))
def test_single_marker_spike_rejected():
 empty=np.full(381,5000.);marker=empty.copy();marker[100]-=500;*_,region=analysis.marker_difference(rows(empty),rows(marker));assert len(region)==0
