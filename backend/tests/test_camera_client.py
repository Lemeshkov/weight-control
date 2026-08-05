import numpy as np

from services.camera_client import CV2_AVAILABLE, CameraClient


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
