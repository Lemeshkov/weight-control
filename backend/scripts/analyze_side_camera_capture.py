"""Inspect one permanent side-camera capture and nearest LiDAR sample distances."""
from __future__ import annotations
import argparse,csv,json
from pathlib import Path
import numpy as np
from config import settings

def rows(path):
 with path.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def lidar_times(root):
 candidates=(root/'lidar'/'raw_scans.jsonl',root.with_suffix('.json'))
 for path in candidates:
  if not path.exists():continue
  data=json.loads(path.read_text(encoding='utf-8')) if path.suffix=='.json' else [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x]
  profiles=data.get('profiles',[]) if isinstance(data,dict) else data
  return np.asarray([int(x['captured_monotonic_ns']) for x in profiles if x.get('captured_monotonic_ns') is not None],dtype=np.int64)
 return np.array([],dtype=np.int64)
def analyze(session_id,base_dir=None):
 root=Path(base_dir or settings.SIDE_CAMERA_SESSION_DATA_DIR)/session_id;cam=rows(root/'camera_side'/'frames.csv');ct=np.asarray([int(x['captured_monotonic_ns']) for x in cam],dtype=np.int64);dt=np.diff(ct)/1e6;positive=dt[dt>0];median=float(np.median(positive)) if len(positive) else None;lt=lidar_times(root);nearest=[]
 if len(ct) and len(lt):
  pos=np.searchsorted(ct,lt);left=np.clip(pos-1,0,len(ct)-1);right=np.clip(pos,0,len(ct)-1);nearest=np.minimum(abs(lt-ct[left]),abs(lt-ct[right]))/1e6
 duration=(ct[-1]-ct[0])/1e9 if len(ct)>1 else 0
 resolutions=sorted({f"{x['width']}x{x['height']}" for x in cam})
 return {'session_id':session_id,'frame_count':len(cam),'duration_s':duration,'actual_fps':(len(cam)-1)/duration if duration>0 else None,'median_dt_ms':median,'p95_dt_ms':float(np.percentile(positive,95)) if len(positive) else None,'max_dt_ms':float(np.max(positive)) if len(positive) else None,'gap_count':int(np.sum(positive>2*median)) if median else 0,'resolution':resolutions,'timestamp_monotonicity':bool(np.all(dt>0)),'duplicate_timestamp_count':len(ct)-len(np.unique(ct)),'lidar_profile_count':len(lt),'median_abs_time_difference_ms':float(np.median(nearest)) if len(nearest) else None,'p95_abs_time_difference_ms':float(np.percentile(nearest,95)) if len(nearest) else None,'max_abs_time_difference_ms':float(np.max(nearest)) if len(nearest) else None,'alignment_semantics':'NEAREST_SAMPLE_TEMPORAL_DISTANCE_NOT_CLOCK_ERROR'}
def main():
 p=argparse.ArgumentParser();p.add_argument('session_id');p.add_argument('--base-dir',type=Path);a=p.parse_args();print(json.dumps(analyze(a.session_id,a.base_dir),indent=2))
if __name__=='__main__':main()
