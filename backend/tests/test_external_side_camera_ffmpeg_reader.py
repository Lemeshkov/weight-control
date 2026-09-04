import io
import json
import subprocess
import threading
import time

import numpy as np

from services.side_camera_ffmpeg_reader import (
    SideCameraFfmpegReader,
    build_ffmpeg_command,
    read_exact,
    sanitize_ffmpeg_text,
)
from services.side_camera_service import SideCameraService, build_credentialed_rtsp_url, parse_rtsp_url


class PartialStream:
    def __init__(self, parts):
        self.parts = list(parts)

    def read(self, size):
        if not self.parts:
            return b""
        return self.parts.pop(0)


class AliveProcess:
    def poll(self):
        return None


class CleanupProcess:
    stdout = io.BytesIO()
    stderr = io.BytesIO()

    def __init__(self, timeout_once=False):
        self.timeout_once = timeout_once
        self.terminated = False
        self.killed = False
        self.waits = 0

    def poll(self):
        return None

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout):
        self.waits += 1
        if self.timeout_once and self.waits == 1:
            raise subprocess.TimeoutExpired("ffmpeg", timeout)
        return 0


class EofProcess(CleanupProcess):
    def poll(self):
        return 0


def make_reader(tmp_path, **kwargs):
    executable = tmp_path / "ffmpeg.exe"
    executable.touch()
    return SideCameraFfmpegReader(
        rtsp_url="rtsp://fake:secret@camera:554/Streaming/Channels/1",
        ffmpeg_path=str(executable), width=2, height=1, **kwargs
    )


def test_rtsp_paths_are_preserved_exactly():
    assert parse_rtsp_url("rtsp://host:554")["path"] == ""
    assert parse_rtsp_url("rtsp://host:554/Streaming/Channels/1")["path"] == "/Streaming/Channels/1"
    assert parse_rtsp_url("rtsp://host:554/ISAPI/Streaming/Channels/101")["path"] == "/ISAPI/Streaming/Channels/101"


def test_credentials_decode_reencode_and_never_enter_status():
    url = build_credentialed_rtsp_url("rtsp://host:554/path", "a@b", "p:x/y")
    assert url == "rtsp://a%40b:p%3Ax%2Fy@host:554/path"
    parsed = parse_rtsp_url(url)
    assert (parsed["username"], parsed["password"]) == ("a@b", "p:x/y")
    service = SideCameraService(enabled=True, rtsp_url=url, client_factory=lambda **kwargs: None)
    assert "a@b" not in json.dumps(service.status()) and "p:x/y" not in json.dumps(service.status())
    assert "secret" not in sanitize_ffmpeg_text("failure rtsp://fake:secret@camera/path")


def test_ffmpeg_command_is_argv_tcp_raw_bgr():
    command = build_ffmpeg_command("ffmpeg.exe", "rtsp://u:p@host/path", 1280, 720)
    assert command[0] == "ffmpeg.exe"
    assert command[command.index("-rtsp_transport") + 1] == "tcp"
    assert command[command.index("-i") + 1] == "rtsp://u:p@host/path"
    assert command[command.index("-f") + 1] == "rawvideo"
    assert command[command.index("-pix_fmt") + 1] == "bgr24"
    assert command[-1] == "pipe:1"


def test_spawn_uses_list_and_shell_false(tmp_path):
    calls = []
    reader = make_reader(tmp_path, popen_factory=lambda command, **kwargs: calls.append((command, kwargs)))
    reader._spawn()
    command, kwargs = calls[0]
    assert isinstance(command, list) and kwargs["shell"] is False and kwargs["stderr"] == subprocess.PIPE


def test_read_exact_assembles_partial_reads_and_rejects_partial_eof():
    assert read_exact(PartialStream([b"ab", b"c", b"def"]), 6) == b"abcdef"
    assert read_exact(PartialStream([b"ab", b""]), 6) is None


def test_timestamp_is_assigned_to_complete_frame_and_not_synthetic(tmp_path, monkeypatch):
    ticks = iter((123, 124))
    reader = make_reader(tmp_path, monotonic_ns=lambda: next(ticks))
    monkeypatch.setattr("services.side_camera_ffmpeg_reader.cv2.imencode", lambda *args, **kwargs: (True, np.array([1, 2], dtype=np.uint8)))
    assert reader.last_frame_monotonic_ns is None
    assert reader._publish_raw(b"\x00" * 6, 123)
    assert reader.last_frame_monotonic_ns == 123
    assert reader._dispatch_queue.get_nowait()["captured_monotonic_ns"] == 123


def test_process_alive_without_a_real_frame_is_not_connected(tmp_path):
    reader = make_reader(tmp_path, monotonic_ns=lambda: 1_000_000)
    reader._process = AliveProcess()
    assert reader.ffmpeg_process_alive is True
    assert reader.is_connected is False


def test_windows_style_cleanup_terminates_then_kills_and_reaps(tmp_path):
    reader = make_reader(tmp_path)
    process = CleanupProcess(timeout_once=True)
    reader._terminate_process(process)
    assert process.terminated and process.killed and process.waits == 2


def test_stderr_is_drained_and_sanitized(tmp_path):
    reader = make_reader(tmp_path)
    reader._drain_stderr(io.BytesIO(b"error rtsp://fake:secret@camera/path\n"))
    assert reader.stderr_diagnostics and "secret" not in reader.stderr_diagnostics[0]


def test_missing_ffmpeg_is_clean_failure(tmp_path):
    reader = SideCameraFfmpegReader(rtsp_url="rtsp://u:p@host/path", ffmpeg_path=str(tmp_path / "missing.exe"), width=2, height=1)
    assert reader.connect() is False
    assert reader.last_error == "FFMPEG_EXECUTABLE_NOT_FOUND"


def test_eof_marks_unhealthy_and_reconnect_wait_is_bounded_not_busy(tmp_path):
    calls = []
    reader = make_reader(tmp_path, reconnect_seconds=0.05)

    def spawn():
        calls.append(time.monotonic())
        process = EofProcess()
        process.stdout = io.BytesIO(b"partial")
        process.stderr = io.BytesIO()
        if len(calls) == 2:
            reader._stop_event.set()
        return process

    reader._spawn = spawn
    reader._supervise()
    assert len(calls) == 2 and calls[1] - calls[0] >= 0.045
    assert reader.rtsp_reconnect_count == 1 and reader.is_connected is False
    assert reader.bad_frames == 1


def test_service_status_exposes_sanitized_external_backend(tmp_path):
    reader = make_reader(tmp_path, monotonic_ns=lambda: 100)
    reader._process = AliveProcess()
    service = SideCameraService(enabled=True, rtsp_url="rtsp://fake:secret@camera/path")
    service.client = reader
    status = service.status()
    assert status["reader_backend"] == "external_ffmpeg"
    assert status["ffmpeg_process_alive"] is True
    assert status["connected"] is False and status["receiving_frames"] is False
    assert "secret" not in json.dumps(status)
