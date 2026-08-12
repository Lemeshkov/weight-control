# Custom detector + ByteTrack offline research

The specialized `weighbridge_vehicle` detector passed the internal development TEST presence gate (recall 94.12%, precision 100%, negative FPR 0%). This is not unseen validation.

The offline pipeline uses `baseline-2/weights/best.pt`, Ultralytics `model.track(..., tracker="bytetrack.yaml", persist=True)`, PCA over normalized bbox centers, and rolling median absolute projected velocity. `TRACK_LOST` is never interpreted as `STOPPED`. Full-frame optical flow is not used.

## Development result

**TRACKING NOT SUITABLE.** No frozen validation candidate is declared.

With the baseline parameters (`stop=0.012/s`, `start=0.035/s`, rolling window 5, stop confirmation 1500 ms, resume confirmation 750 ms), the correctly marked `c178…` pass had 80.82% visible frames inside ENTER→EXIT, one track ID in that interval, but a 28-frame gap. It predicted STOP 1547 ms before the manual marker, RESUME 1813 ms late, accumulated 3360 ms false STOP and 7000 ms UNKNOWN, and reached only 71.56% correct labeled time.

The `0700…` no-stop development pass has no operator markers, so full ground-truth duration metrics cannot be claimed. In the observed sequence it produced two STOPPED transitions, including a 2703 ms stopped run, and fragmented into four IDs. This violates the no-stop criterion.

A development sweep found thresholds that remove the two no-stop STOP transitions, but they still stop about 1.8 seconds early on `c178…`, retain 7 seconds UNKNOWN, and do not produce a valid post-marker STOP transition. Threshold tuning cannot repair the detector/track coverage limitation.

CPU medians were about 304–306 ms YOLO inference plus 32 ms combined tracking/I/O overhead; capacity was roughly 3 FPS. Therefore 5, 10, and 20 FPS budgets (200/100/50 ms) are not met on this CPU. Trajectory processing itself is negligible (<0.1 ms/frame).

Before a frozen candidate, collect fully marked no-stop passes and improve offline detector/tracker coverage at partial entry/exit and reconnect boundaries. Required unseen validation after a future freeze: at least three stop/resume vehicles, two no-stop vehicles, and one adverse shadow/light pass, all with ENTER/STOP/RESUME/EXIT where applicable.

Run:

```powershell
..\venv_weight\Scripts\python.exe scripts\research_weighbridge_vehicle_tracking.py ..\diagnostics\c1788407a99c40a88e4d9f85b5435ca5 --scenario stop-resume --weights ..\diagnostics\training\weighbridge_vehicle\runs\baseline-2\weights\best.pt
```
