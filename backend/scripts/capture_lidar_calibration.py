"""Manual maintenance-only capture of full LMS511 calibration profiles."""
from __future__ import annotations
import argparse,json,os,socket,struct,sys,time,uuid
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.lidar_client import LidarClient

WARNING="""\n============================================================
CALIBRATION CAPTURE ONLY
ENSURE WEIGHBRIDGE IS CLEAR
NO VEHICLE SHOULD ENTER DURING CAPTURE
============================================================"""
CANONICAL={"empty_before":"empty_before","empty":"empty_before","marker":"marker","empty_after":"empty_after"}
HEIGHT_MM=5650;HEIGHT_UNCERTAINTY_MM=50
def decode_scale_factor(raw:int)->float:return struct.unpack(">f",int(raw).to_bytes(4,"big",signed=False))[0]
def physical_ranges(raw,scale,offset):return [None if v is None or int(v)<=0 else float(v)*scale+offset for v in raw]
def scan_record(parsed,capture_id,requested_mode,sequence,captured_ns,captured_wall,latency_ms=None):
 scale=decode_scale_factor(parsed["scale_factor_raw"]);physical=physical_ranges(parsed["ranges_raw"],scale,parsed["scale_offset_raw"]);mask=[x is not None for x in physical]
 return {"capture_id":capture_id,"mode":requested_mode,"sequence":sequence,"captured_monotonic_ns":captured_ns,"captured_wall_time":captured_wall,"start_angle_deg":parsed["start_angle_deg"],"end_angle_deg":parsed["end_angle_deg"],"angular_step_deg":parsed["angular_step_deg"],"beam_count":parsed["beam_count"],"ranges_raw":parsed["ranges_raw"],"scale_factor_raw":parsed["scale_factor_raw"],"scale_factor_decoded":scale,"scale_offset_raw":parsed["scale_offset_raw"],"ranges_physical_mm":physical,"valid_mask_raw":mask,"invalid_reason":[None if ok else "RAW_ZERO_OR_NEGATIVE" for ok in mask],"telegram_acquisition_latency_ms":latency_ms,"production_action_triggered":False}
def backend_connection_detected(host,port):
 try:
  import psutil
  for connection in psutil.net_connections(kind="tcp"):
   if connection.status==psutil.CONN_ESTABLISHED and connection.raddr and connection.raddr.ip==host and connection.raddr.port==port and connection.pid!=os.getpid():return True
  return False
 except Exception:return None
def receive_scan(sock):
 sock.sendall(b"\x02sRN LMDscandata\x03");chunks=[];started=time.monotonic_ns()
 while True:
  part=sock.recv(65535)
  if not part:raise ConnectionError("LMS511 closed connection")
  chunks.append(part)
  if b"\x03" in part:break
 data=b"".join(chunks);start=data.find(b"\x02");end=data.find(b"\x03",start+1)
 if start<0 or end<0:raise ValueError("incomplete STX/ETX telegram")
 decoded=data[start+1:end].decode("ascii",errors="strict")
 if "sRA LMDscandata" not in decoded:raise ValueError("unexpected LMS511 response")
 return decoded,(time.monotonic_ns()-started)/1e6
def acquire(args,client):
 requested=args.mode;canonical=CANONICAL[requested];capture_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+canonical+"_"+uuid.uuid4().hex[:8];base=Path(args.output_root);target=base/capture_id;base.mkdir(parents=True,exist_ok=True)
 lock=base/".capture.lock"
 try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
 except FileExistsError:raise RuntimeError(f"CALIBRATION_CAPTURE_ALREADY_RUNNING — remove stale lock only after verifying no capture is active: {lock}")
 os.write(fd,str(os.getpid()).encode());os.close(fd);started_wall=datetime.now(timezone.utc);started_ns=time.monotonic_ns();records=[];errors=[]
 try:
  target.mkdir(exist_ok=False)
  with socket.create_connection((client.host,client.port),timeout=args.connect_timeout) as sock:
   sock.settimeout(args.scan_timeout);sequence=0
   while (time.monotonic_ns()-started_ns)/1e9<args.duration:
    try:
     if backend_connection_detected(client.host,client.port) is True:raise RuntimeError("LIDAR_IN_USE — backend connection appeared during capture")
     telegram,latency=receive_scan(sock);captured=time.monotonic_ns();parsed=client.parse_diagnostic_scan(telegram);record=scan_record(parsed,capture_id,requested,sequence,captured,datetime.now(timezone.utc).isoformat(),latency)
     if record["beam_count"]!=381 or len(record["ranges_raw"])!=381:raise ValueError(f"unexpected beam count {record['beam_count']}")
     records.append(record);sequence+=1
    except Exception as exc:errors.append({"at":datetime.now(timezone.utc).isoformat(),"error":type(exc).__name__,"message":str(exc)});break
  if not records:raise RuntimeError("no valid full profiles captured")
  with (target/"raw_scans.jsonl").open("w",encoding="utf-8") as f:
   for row in records:f.write(json.dumps(row,separators=(",",":"))+"\n")
  first=records[0];ended=datetime.now(timezone.utc);metadata={"capture_id":capture_id,"requested_mode":requested,"capture_mode":canonical,"sensor":"SICK LMS511","purpose":"lidar_weighbridge_2d_calibration","duration_requested_sec":args.duration,"profile_count":len(records),"start_wall_time":started_wall.isoformat(),"end_wall_time":ended.isoformat(),"known_geometry":{"lidar_height_above_platform_mm":HEIGHT_MM,"lidar_height_uncertainty_mm":HEIGHT_UNCERTAINTY_MM},"scan_geometry":{k:first[k] for k in ("start_angle_deg","end_angle_deg","angular_step_deg","beam_count")},"errors":errors,"production_action_triggered":False};(target/"metadata.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8");(target/"summary.json").write_text(json.dumps({"capture_id":capture_id,"mode":requested,"canonical_mode":canonical,"profile_count":len(records),"output":str(target),"production_action_triggered":False},indent=2),encoding="utf-8");return target,len(records)
 finally:
  try:lock.unlink()
  except FileNotFoundError:pass
def parser():
 p=argparse.ArgumentParser(description="Maintenance-only LMS511 calibration capture");p.add_argument("--mode",required=True,choices=tuple(CANONICAL));p.add_argument("--duration",type=float,required=True);p.add_argument("--output-root",default=os.getenv("LIDAR_CALIBRATION_DATA_DIR",r"C:\weight-control-data\lidar_calibration"));p.add_argument("--confirm-clear",action="store_true",help="confirm weighbridge is clear for requested mode");p.add_argument("--confirm-backend-stopped",action="store_true");p.add_argument("--connect-timeout",type=float,default=3);p.add_argument("--scan-timeout",type=float,default=3);return p
def main():
 args=parser().parse_args();print(WARNING,flush=True)
 if not 1<=args.duration<=300:raise SystemExit("duration must be between 1 and 300 seconds")
 if not args.confirm_clear:raise SystemExit("REFUSED: pass --confirm-clear only after physically verifying the requested scene")
 if not args.confirm_backend_stopped:raise SystemExit("LIDAR_IN_USE — stop backend before calibration capture, then pass --confirm-backend-stopped")
 client=LidarClient();in_use=backend_connection_detected(client.host,client.port)
 if in_use is True:raise SystemExit("LIDAR_IN_USE — stop backend before calibration capture")
 if in_use is None:print("WARNING: OS connection ownership could not be inspected; relying on explicit backend-stopped confirmation",flush=True)
 try:target,count=acquire(args,client)
 except (ConnectionRefusedError,TimeoutError,socket.timeout,OSError) as exc:raise SystemExit(f"LIDAR_IN_USE_OR_UNREACHABLE — stop backend and verify LMS511 connectivity: {exc}")
 print(f"CAPTURE COMPLETE profiles={count} output={target}")
if __name__=="__main__":main()
