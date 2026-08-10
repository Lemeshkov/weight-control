import numpy as np
import logging
from requests.auth import HTTPDigestAuth

from services.camera_client import CV2_AVAILABLE, CameraClient, cv2


def test_get_frame_reuses_cached_jpeg(monkeypatch):
    if not CV2_AVAILABLE:
        return

    client = CameraClient()
    client.is_connected = True
    assert client._publish_frame(np.zeros((480, 640, 3), dtype=np.uint8))

    def unexpected_encode(*args, **kwargs):
        raise AssertionError("get_frame must not encode per HTTP client")

    monkeypatch.setattr("services.camera_client.cv2.imencode", unexpected_encode)
    first = client.get_frame()
    second = client.get_frame()

    assert first is not None
    assert second is not None
    assert first["data"] is second["data"]
    assert first["width"] == 640
    assert first["height"] == 480


def test_disconnected_camera_returns_no_frame():
    client = CameraClient()
    assert client.get_frame() is None


def test_snapshot_uses_one_persistent_digest_request_and_reports_timing(monkeypatch):
    if not CV2_AVAILABLE:
        return
    client = CameraClient(camera_type="ip", username="user", password="secret")
    calls = []

    class Response:
        status_code = 200
        content = b"jpeg"

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(client._http, "get", fake_get)
    content, timing = client.get_snapshot_with_timing()

    assert content == b"jpeg"
    assert len(calls) == 1
    assert isinstance(calls[0][1]["auth"], HTTPDigestAuth)
    assert "@" not in calls[0][0]
    assert timing["camera_http_response_received_monotonic_ns"] >= timing["camera_acquisition_started_monotonic_ns"]


def test_snapshot_capture_publishes_without_success_sleep(monkeypatch):
    if not CV2_AVAILABLE:
        return
    client = CameraClient(camera_type="ip")
    client._snapshot_mode = True
    encoded = cv2.imencode(".jpg", np.zeros((10, 10, 3), dtype=np.uint8))[1].tobytes()
    client.get_snapshot_with_timing = lambda: (encoded, {"camera_acquisition_started_monotonic_ns": 1,
                                                          "camera_http_response_received_monotonic_ns": 2})
    samples = []

    def listener(sample):
        samples.append(sample)
        client._stop_event.set()

    client.add_frame_listener(listener)
    monkeypatch.setattr("services.camera_client.time.sleep", lambda seconds: (_ for _ in ()).throw(
        AssertionError(f"successful snapshot path must not sleep: {seconds}")
    ))
    client._capture_loop()

    assert len(samples) == 1
    assert samples[0]["camera_decode_completed_monotonic_ns"] >= 2
    assert samples[0]["frame_published_monotonic_ns"] >= samples[0]["camera_decode_completed_monotonic_ns"]


class FakeCapture:
    def __init__(self, reads, opened=True):
        self.reads = list(reads)
        self.opened = opened
        self.released = False

    def isOpened(self):
        return self.opened and not self.released

    def read(self):
        return self.reads.pop(0) if self.reads else (False, None)

    def set(self, *_args):
        return True

    def release(self):
        self.released = True


def test_rtsp_mode_publishes_every_read_frame_to_subscriber():
    if not CV2_AVAILABLE:
        return
    client = CameraClient(camera_type="ip", capture_mode="rtsp", rtsp_fallback_to_snapshot=False)
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    client.cap = FakeCapture([(True, frame), (True, frame), (True, frame)])
    samples = []

    def listener(sample):
        samples.append(sample)
        if len(samples) == 3:
            client._stop_event.set()

    client.add_frame_listener(listener)
    client._capture_loop()

    assert [sample["sequence_number"] for sample in samples] == [1, 2, 3]
    assert all("camera_frame_read_started_monotonic_ns" in sample for sample in samples)
    assert client._capture_thread is None


def test_rtsp_reconnects_after_failed_reads(monkeypatch):
    if not CV2_AVAILABLE:
        return
    client = CameraClient(camera_type="ip", capture_mode="rtsp", rtsp_fallback_to_snapshot=False,
                          rtsp_reconnect_seconds=0)
    client.cap = FakeCapture([(False, None), (False, None), (False, None)])
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    reopened = []

    def open_rtsp():
        reopened.append(True)
        client.cap = FakeCapture([(True, frame)])
        client.active_capture_mode = "rtsp"
        return True

    monkeypatch.setattr(client, "_open_rtsp", open_rtsp)
    client.add_frame_listener(lambda _sample: client._stop_event.set())
    client._capture_loop()

    assert len(reopened) == 1
    assert client.rtsp_reconnect_count == 1
    assert client.rtsp_failed_reads == 3
    assert client.is_connected is True


def test_rtsp_credentials_are_encoded_and_never_logged(monkeypatch, caplog):
    if not CV2_AVAILABLE:
        return
    secret = "p@ss word"
    client = CameraClient(camera_type="ip", ip="10.0.0.1", username="operator", password=secret,
                          capture_mode="rtsp")
    opened_urls = []

    def video_capture(url, *_args):
        opened_urls.append(url)
        return FakeCapture([], opened=False)

    monkeypatch.setattr("services.camera_client.cv2.VideoCapture", video_capture)
    with caplog.at_level(logging.INFO):
        assert client._open_rtsp() is False

    assert "operator:p%40ss%20word@" in opened_urls[0]
    assert secret not in caplog.text
    assert "p%40ss%20word" not in caplog.text
