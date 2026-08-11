# Offline vehicle detection and tracking research

## Scope and environment

Only recorded JPEG/LiDAR diagnostics were read. Production CameraClient, capture,
coordinator, FSM, reconstruction, API, database and frontend were not changed.

- Ultralytics `8.4.117`;
- pretrained `yolo11n.pt` (weights stored only under untracked `diagnostics/`);
- COCO classes: `car=2`, `bus=5`, `truck=7`;
- audit confidence `0.10`, working confidence `0.25`;
- input `640`, CPU, Torch `2.1.0`, OpenCV `4.8.1`;
- ByteTrack eligibility gate: detection rate at least 80%.

## Detection audit

The correctly marked session `c1788407a99c40a88e4d9f85b5435ca5` contains 521
frames and 146 frames inside `[VEHICLE_ENTERED, VEHICLE_EXITED)`. YOLO detected the
target at confidence >=0.25 in only 15 active frames (10.27%); 131 active frames were
missed. At the 0.10 audit floor it detected 18 active frames. Confidence across these
detections: median 0.450, p10 0.164, p90 0.629. Detections alternate between `bus` and
`truck`, confirming that the top-down mining truck differs from ordinary COCO views.

Two detections are outside the annotated vehicle interval. They are reported as
outside-interval detections, not asserted to be visually false without additional
frame-level object annotation.

Legacy datasets lack entry/exit markers and therefore have `INCOMPLETE` presence
ground truth. Their raw full-session counts at confidence >=0.25 are:

- TEST B: 14 of 173 total frames;
- `c65c0b…`: 86 of 1153 total frames;
- `0700fa…`: 26 of 477 total frames.

They cannot be used for target recall or false-positive rate because the target's
presence interval is unknown.

## Tracking decision

ByteTrack and BoT-SORT were not run. With 10.27% detector recall, track continuity,
trajectory STOP/RESUME, bbox optical flow, and trajectory+flow fusion would be
dominated by missing detections. Missing detection is written as `TRACK_LOST` and maps
to LiDAR action `UNKNOWN`, never `STOPPED/FREEZE`.

Consequently STOP delay, RESUME delay, false STOP/MOVING and no-stop tracking metrics
are unavailable rather than fabricated. A no-stop session with correct entry/exit
markers is also still required.

## Comparison

| Algorithm | Presence / recall | STOP delay | RESUME delay | False STOP | Correct fraction | Result |
|---|---:|---:|---:|---:|---:|---|
| Frozen full-frame Farneback | marker-gated | 9157 ms | 125 ms | 3015 ms | 66.58% | FAIL |
| YOLO11n + trajectory | 10.27% detector recall | unavailable | unavailable | unavailable | unavailable | tracking skipped |
| YOLO11n + bbox flow | 10.27% detector recall | unavailable | unavailable | unavailable | unavailable | tracking skipped |
| YOLO11n + trajectory + bbox flow | 10.27% detector recall | unavailable | unavailable | unavailable | unavailable | tracking skipped |

YOLO CPU inference median is 240.7 ms and p90 344.8 ms on the correctly marked
session, with end-to-end audit throughput 3.18 FPS on this development machine. This
supports roughly 3 FPS here, not 5/10/20 FPS. It is not a production hardware claim.

## Conclusion and next experiment

**A. YOLO DETECTION NOT SUITABLE** for the current pretrained YOLO11n/COCO setup.
No frozen validation candidate can be formed.

Next options, in order:

1. audit a larger pretrained YOLO model on a sampled subset;
2. compare another pretrained detector with stronger overhead/industrial-vehicle data;
3. create a small manually annotated vehicle bbox dataset from this camera;
4. fine-tune a custom `weighbridge_vehicle` class in a separate future task;
5. compare classical background/foreground segmentation plus an established tracker.

The next controlled data must include a correctly marked no-stop pass and additional
truck types/lighting. Training is deliberately not performed in this stage.

Future architecture can retain one CameraClient producer with independent consumers:
vehicle detector/tracker and cargo classifier. No second capture loop is necessary.
