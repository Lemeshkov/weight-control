# Side camera setup

Side camera is a permanent optional longitudinal visual sensor. Its production acquisition backend is one supervised external FFmpeg process shared by preview, session recording and diagnostics. Until metric odometry is separately validated, its raw data never changes production volume, speed or longitudinal displacement.

Configure secrets only in the server environment:

```env
SIDE_CAMERA_ENABLED=true
SIDE_CAMERA_STREAM_URL=rtsp://host/path
SIDE_CAMERA_USERNAME=<secret>
SIDE_CAMERA_PASSWORD=<secret>
SIDE_CAMERA_TARGET_FPS=15
SIDE_CAMERA_FFMPEG_PATH=tools/ffmpeg/ffmpeg-9.0.1-essentials_build/bin/ffmpeg.exe
SIDE_CAMERA_FRAME_WIDTH=1280
SIDE_CAMERA_FRAME_HEIGHT=720
```

`SIDE_CAMERA_STREAM_URL` must contain the verified path exactly; an empty/root path is not replaced with a vendor-specific default. If authentication is embedded in that URL, status and manifests redact it. The legacy `CAMERA_SIDE_*` variables remain supported. The side reader always requests RTSP over TCP and does not silently fall back to OpenCV RTSP.

After restart, check `GET /api/cameras/status`: `side.reader_backend=external_ffmpeg`, `connected`, `receiving_frames`, `actual_fps`, `frame_age_ms`, `ffmpeg_process_alive` and `last_error_sanitized`. `connected` requires recent real frames, not merely a live process. Perform one complete pass and verify:

```text
backend/data/lidar_passes/<session_id>/camera_side/frames/
backend/data/lidar_passes/<session_id>/camera_side/frames.csv
backend/data/lidar_passes/<session_id>/camera_side/manifest.json
```

The synchronization key is `captured_monotonic_ns`. Python assigns it from `time.monotonic_ns()` only after one complete decoded BGR frame has arrived from FFmpeg. It is not camera exposure time; camera DTS/PTS are not authoritative. Inspect capture quality with:

```powershell
python backend/scripts/analyze_side_camera_capture.py <session_id>
```

Run an isolated live 60-second acquisition check from `backend` without placing a password in the command line:

```powershell
python scripts/test_side_camera_ffmpeg_reader.py --seconds 60
```

The script reads `.env`, never prints credentials, and requires actual frames plus reasonable cadence for `STATUS=PASS`. On disconnect the reader terminates, waits for, and if necessary kills/reaps FFmpeg on Windows. Missing FFmpeg, camera outages and reconnects affect only this optional sensor; weighing, LiDAR, top camera and the current volume algorithm continue independently.

Future derived data belongs separately under `derived/side_camera_motion/trajectory.csv` with columns `timestamp_ns,x_m,velocity_mps,tracking_confidence,source_frame_index`. X(t), speed and DeltaL are not implemented here, and the current capture layer does not create or populate trajectory values.
