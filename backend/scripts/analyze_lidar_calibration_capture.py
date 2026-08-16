"""Offline EMPTY→MARKER→EMPTY calibration-capture comparison."""
import argparse,csv,json,sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

def load_capture(path):
 meta=json.loads((path/"metadata.json").read_text(encoding="utf-8"));rows=[json.loads(x) for x in (path/"raw_scans.jsonl").read_text(encoding="utf-8").splitlines() if x];return meta,rows
def matrix(rows):return np.asarray([[np.nan if x is None else float(x) for x in r["ranges_physical_mm"]] for r in rows])
def robust(rows):
 values=matrix(rows);median=np.nanmedian(values,axis=0);mad=np.nanmedian(np.abs(values-median),axis=0);return median,mad,np.mean(np.isfinite(values),axis=0)
def compare_empty(before,after):
 a,_,_=robust(before);b,_,_=robust(after);delta=np.abs(a-b);finite=delta[np.isfinite(delta)];return {"median_beam_delta_mm":float(np.median(finite)),"p90_delta_mm":float(np.percentile(finite,90)),"p99_delta_mm":float(np.percentile(finite,99)),"fraction_beams_changed_gt30":float(np.mean(finite>30)),"fraction_beams_changed_gt100":float(np.mean(finite>100))}
def contiguous_regions(mask):
 ids=np.flatnonzero(mask);return [x for x in np.split(ids,np.where(np.diff(ids)>1)[0]+1) if len(x)] if len(ids) else []
def marker_difference(empty_rows,marker_rows):
 empty,noise,valid=robust(empty_rows);marker,marker_noise,marker_valid=robust(marker_rows);delta=empty-marker;threshold=np.maximum(6*noise,np.nanpercentile(noise[np.isfinite(noise)],90));regions=[x for x in contiguous_regions((delta>threshold)&(valid>=.8)&(marker_valid>=.8)) if len(x)>=2];best=max(regions,key=lambda x:(len(x),float(np.nanmedian(delta[x]))),default=np.array([],int));return empty,marker,noise,marker_noise,valid,marker_valid,delta,best
def write(path,rows):
 if not rows:path.write_text("",encoding="utf-8");return
 with path.open("w",encoding="utf-8",newline="") as f:w=csv.DictWriter(f,rows[0]);w.writeheader();w.writerows(rows)
def main():
 p=argparse.ArgumentParser();p.add_argument("--empty-before",type=Path,required=True);p.add_argument("--empty-after",type=Path,required=True);p.add_argument("--marker",type=Path);p.add_argument("--output",type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);captures=[]
 for role,path in (("empty_before",a.empty_before),("marker",a.marker),("empty_after",a.empty_after)):
  if path:meta,rows=load_capture(path);captures.append({"role":role,"capture_id":meta["capture_id"],"profile_count":len(rows),"path":str(path)});globals()[role+"_rows"]=rows
 quality=compare_empty(empty_before_rows,empty_after_rows);invalid=quality["p99_delta_mm"]>100 or quality["fraction_beams_changed_gt100"]>.05;empty,_,valid=robust(empty_before_rows+empty_after_rows);angles=-5+np.arange(len(empty))*.5;profile=[{"beam_index":i,"angle_deg":angles[i],"median_range_mm":empty[i],"valid_fraction":valid[i]} for i in range(len(empty))];write(a.output/"capture_inventory.csv",captures);write(a.output/"empty_before_vs_after.csv",[quality]);write(a.output/"empty_median_profile.csv",profile);marker_found=False;marker_rows_csv=[];anchor=[]
 if a.marker and not invalid:
  e,m,en,mn,ev,mv,d,region=marker_difference(empty_before_rows+empty_after_rows,marker_rows);marker_rows_csv=[{"beam_index":i,"angle_deg":angles[i],"empty_range_mm":e[i],"marker_range_mm":m[i],"delta_mm":d[i],"empty_variability":en[i],"marker_variability":mn[i],"valid_fraction":min(ev[i],mv[i])} for i in range(len(e))];marker_found=len(region)>0
  if marker_found:anchor=[{"beam_start":int(region[0]),"beam_end":int(region[-1]),"center_beam":int(region[len(region)//2]),"center_angle_deg":angles[region[len(region)//2]],"empty_range_mm":e[region[len(region)//2]],"marker_range_mm":m[region[len(region)//2]]}]
 write(a.output/"marker_difference.csv",marker_rows_csv);write(a.output/"platform_anchor_candidate.csv",anchor);summary={**quality,"status":"CALIBRATION_CAPTURE_INVALID" if invalid else "VALID_EMPTY_PAIR","marker_required":not marker_found,"marker_found":marker_found,"marker_beams":None if not anchor else f"{anchor[0]['beam_start']}..{anchor[0]['beam_end']}","production_action_triggered":False};(a.output/"analysis_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
 fig,ax=plt.subplots();ax.plot(angles,robust(empty_before_rows)[0],label="before");ax.plot(angles,robust(empty_after_rows)[0],label="after");ax.legend();ax.grid();ax.set(xlabel="angle deg",ylabel="range mm");fig.savefig(a.output/"empty_before_after_overlay.png",dpi=150);plt.close(fig)
 if marker_rows_csv:
  fig,ax=plt.subplots();ax.plot(angles,[x["delta_mm"] for x in marker_rows_csv]);ax.grid();ax.set(xlabel="angle deg",ylabel="empty-marker mm");fig.savefig(a.output/"marker_difference_by_beam.png",dpi=150);plt.close(fig)
 print(json.dumps(summary,indent=2))
if __name__=="__main__":main()
