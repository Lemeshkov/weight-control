import numpy as np
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
