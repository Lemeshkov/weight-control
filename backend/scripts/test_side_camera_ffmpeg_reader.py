"""Safe live side-camera acquisition diagnostic; credentials are read from config only."""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings  # noqa: E402
from services.side_camera_service import SideCameraService, parse_rtsp_url  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=60.0)
    args = parser.parse_args()
    duration = max(1.0, args.seconds)
    samples: list[int] = []
    service = SideCameraService(enabled=True)
    service.add_frame_listener(lambda sample: samples.append(int(sample["captured_monotonic_ns"])))
    started = time.monotonic()
    launched = service.start()
    try:
        while time.monotonic() - started < duration:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        service.stop()
    elapsed = time.monotonic() - started
    status = service.status()
    intervals = [(b - a) / 1_000_000 for a, b in zip(samples, samples[1:])]
    measured = (len(samples) - 1) / ((samples[-1] - samples[0]) / 1e9) if len(samples) > 1 else 0.0
    expected = settings.SIDE_CAMERA_TARGET_FPS
    result = "PASS" if launched and measured >= expected * 0.8 and len(samples) >= duration * expected * 0.75 else "WARN" if samples else "FAIL"
    path = parse_rtsp_url(settings.CAMERA_SIDE_RTSP_URL)["path"] if settings.CAMERA_SIDE_RTSP_URL else settings.CAMERA_SIDE_RTSP_PATH
    values = {
        "HOST": settings.CAMERA_SIDE_HOST,
        "PATH": path,
        "BACKEND": "external_ffmpeg",
        "RESOLUTION": f"{settings.SIDE_CAMERA_FRAME_WIDTH}x{settings.SIDE_CAMERA_FRAME_HEIGHT}",
        "FRAMES": len(samples),
        "ELAPSED": f"{elapsed:.3f}",
        "MEASURED_FPS": f"{measured:.3f}",
        "BAD_FRAMES": getattr(service.client, "bad_frames", 0) if service.client else 0,
        "RECONNECTS": status["reconnect_count"],
        "MAX_GAP_MS": f"{max(intervals):.3f}" if intervals else "N/A",
        "P50_INTERVAL_MS": f"{statistics.median(intervals):.3f}" if intervals else "N/A",
        "P95_INTERVAL_MS": f"{statistics.quantiles(intervals, n=20)[18]:.3f}" if len(intervals) >= 20 else "N/A",
        "STATUS": result,
    }
    for key, value in values.items():
        print(f"{key}={value}")
    return 0 if result == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
