import unittest
from unittest.mock import Mock, patch

from services.camera_client import CameraClient


class CameraResilienceTests(unittest.TestCase):
    @patch("services.camera_client.Thread")
    def test_offline_ip_camera_starts_background_retry(self, thread_class):
        thread = thread_class.return_value
        client = CameraClient(camera_type="ip", username="user", password="pass")
        client.get_snapshot = Mock(return_value=None)

        self.assertTrue(client.connect())
        self.assertTrue(client._snapshot_mode)
        self.assertFalse(client.is_connected)
        thread.start.assert_called_once()

    def test_snapshot_retries_with_digest_auth(self):
        client = CameraClient(camera_type="ip", username="user", password="pass")
        unauthorized = Mock(status_code=401)
        success = Mock(status_code=200, content=b"jpeg")
        client._http.get = Mock(side_effect=[unauthorized, success])

        self.assertEqual(client.get_snapshot(), b"jpeg")
        self.assertEqual(client._http.get.call_count, 2)

    def test_connect_is_idempotent_while_worker_is_alive(self):
        client = CameraClient(camera_type="ip")
        client._capture_thread = Mock()
        client._capture_thread.is_alive.return_value = True

        self.assertTrue(client.connect())
        client._capture_thread.is_alive.assert_called_once()



    def test_http_session_ignores_environment_proxy(self):
        client = CameraClient(camera_type="ip")

        self.assertFalse(client._http.trust_env)

if __name__ == "__main__":
    unittest.main()
