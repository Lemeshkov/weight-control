# Side camera setup

Side camera is a permanent optional capture sensor. Until metric odometry is separately validated, its data never changes the production volume result.

Configure secrets only in the server environment:

```env
SIDE_CAMERA_ENABLED=true
SIDE_CAMERA_STREAM_URL=rtsp://host/path
SIDE_CAMERA_USERNAME=<secret>
SIDE_CAMERA_PASSWORD=<secret>
SIDE_CAMERA_TARGET_FPS=15
```

`SIDE_CAMERA_STREAM_URL` must contain a verified camera path. If authentication is embedded in that URL, status and manifests redact it. The legacy `CAMERA_SIDE_*` variables remain supported.

After restart, check `GET /api/cameras/status`: `side.configured`, `connected`, `receiving_frames`, `actual_fps` and `last_error`. Perform one complete pass and verify:

```text
backend/data/lidar_passes/<session_id>/camera_side/frames/
backend/data/lidar_passes/<session_id>/camera_side/frames.csv
backend/data/lidar_passes/<session_id>/camera_side/manifest.json
```

The synchronization key is `captured_monotonic_ns`, recorded on the host near receive/decode time. It is not camera exposure time. Inspect capture quality with:

```powershell
python backend/scripts/analyze_side_camera_capture.py <session_id>
```

Future derived data belongs separately under `derived/side_camera_motion/trajectory.csv` with columns `timestamp_ns,x_m,velocity_mps,tracking_confidence,source_frame_index`. The current capture layer does not create or populate trajectory values.
