# backend/services/camera_client.py

import logging
import time
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from threading import Thread, Event, Lock
import requests
from requests.auth import HTTPDigestAuth
import numpy as np

# ⭐ Оберните импорт cv2 в try/except
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    cv2 = None
    logging.warning("⚠️ OpenCV (cv2) не доступен. Камера будет отключена.")

logger = logging.getLogger(__name__)


class CameraClient:
    """Клиент для работы с камерой (поддерживает USB, Webcam, IP cameras)"""

    def __init__(self,
                    camera_type: str = "webcam",
                    ip: str = "192.168.1.64",
                    port: int = 80,
                    username: str = "",
                    password: str = "",
                    rtsp_path: str = "/Streaming/Channels/101"):
        self.camera_type = camera_type
        self.ip = ip
        self.port = port
        self.username = username
        self.password = password
        self.rtsp_path = rtsp_path
        self.cap: Optional[cv2.VideoCapture] = None if not CV2_AVAILABLE else None
        self.is_connected = False
        self._frame_lock = Lock()
        self._current_jpeg: Optional[bytes] = None
        self._frame_width = 0
        self._frame_height = 0
        self.frame_timestamp: Optional[datetime] = None
        self._stop_event = Event()
        self._capture_thread: Optional[Thread] = None
        self._error_count = 0
        self._snapshot_mode = False
        self._http = requests.Session()
        # The camera is on the LAN; environment proxies can intercept local requests.
        self._http.trust_env = False
        self._frame_sequence = 0
        self._last_frame_monotonic_ns = 0
        self._frame_listeners = []

    def add_frame_listener(self, listener) -> None:
        """Subscribe to already captured frames; this never starts another capture loop."""
        with self._frame_lock:
            if listener not in self._frame_listeners:
                self._frame_listeners.append(listener)

    def remove_frame_listener(self, listener) -> None:
        with self._frame_lock:
            if listener in self._frame_listeners:
                self._frame_listeners.remove(listener)

    def _publish_frame(self, frame: np.ndarray) -> bool:
        """Encode once in the capture thread and publish the latest JPEG."""
        try:
            if frame is None or frame.size == 0:
                return False
            if frame.shape[1] > 1024:
                scale = 1024 / frame.shape[1]
                frame = cv2.resize(frame, (1024, int(frame.shape[0] * scale)))
            ok, buffer = cv2.imencode(
                ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70]
            )
            if not ok:
                return False
            jpeg = buffer.tobytes()
            captured_at = datetime.now(timezone.utc)
            captured_monotonic_ns = max(time.monotonic_ns(), self._last_frame_monotonic_ns + 1)
            self._last_frame_monotonic_ns = captured_monotonic_ns
            with self._frame_lock:
                self._frame_sequence += 1
                sequence = self._frame_sequence
                self._current_jpeg = jpeg
                self._frame_width = int(frame.shape[1])
                self._frame_height = int(frame.shape[0])
                self.frame_timestamp = captured_at
                listeners = list(self._frame_listeners)
            sample = {
                "sequence_number": sequence,
                "captured_utc": captured_at.isoformat(),
                "captured_monotonic_ns": captured_monotonic_ns,
                "processing_completed_monotonic_ns": time.monotonic_ns(),
                "jpeg": jpeg,
                "width": int(frame.shape[1]),
                "height": int(frame.shape[0]),
            }
            for listener in listeners:
                try:
                    listener(sample)
                except Exception:
                    logger.exception("Camera frame listener failed")
            return True
        except Exception as exc:
            logger.warning("Camera frame encode failed: %s", type(exc).__name__)
            return False

    def _get_stream_url(self) -> str:
        """Формирует URL для потока"""
        if not CV2_AVAILABLE:
            return "0"

        if self.camera_type == "usb":
            return "0"
        elif self.camera_type == "webcam":
            return "0"
        elif self.camera_type == "ip":
            if self.username and self.password:
                return f"rtsp://{self.username}:{self.password}@{self.ip}:554{self.rtsp_path}"
            else:
                return f"rtsp://{self.ip}:554{self.rtsp_path}"
        return "0"

    def _get_snapshot_url(self) -> str:
        """Получить снимок через HTTP (альтернативный метод)"""
        if self.username and self.password:
            return f"http://{self.username}:{self.password}@{self.ip}:{self.port}/ISAPI/Streaming/channels/101/picture"
        return f"http://{self.ip}:{self.port}/ISAPI/Streaming/channels/101/picture"

    def get_snapshot(self) -> Optional[bytes]:
        """Получить JPEG снимок через HTTP (более стабильно)"""
        if not CV2_AVAILABLE:
            return None

        try:
            url = self._get_snapshot_url()
            response = self._http.get(url, timeout=(2, 3), auth=(self.username, self.password))
            if response.status_code == 401 and self.username:
                response = self._http.get(
                    url,
                    timeout=(2, 3),
                    auth=HTTPDigestAuth(self.username, self.password),
                )
            if response.status_code == 200:
                return response.content
            else:
                logger.warning(f"HTTP snapshot failed: {response.status_code}")
                return None
        except Exception as e:
            logger.debug(f"Snapshot error: {e}")
            return None

    def connect(self) -> bool:
        """Подключение к камере"""
        if not CV2_AVAILABLE:
            logger.error("❌ OpenCV не доступен, подключение к камере невозможно")
            return False
        try:
            cv2.setLogLevel(0)
        except:
            pass

        if self._capture_thread and self._capture_thread.is_alive():
            return True

        try:
            if self.camera_type == "ip":
                # Hikvision HTTP snapshots are bounded by a request timeout and
                # cannot freeze the capture thread like a blocking RTSP read.
                snapshot = self.get_snapshot()
                if snapshot:
                    frame = cv2.imdecode(np.frombuffer(snapshot, np.uint8), cv2.IMREAD_COLOR)
                    if frame is not None:
                        self._publish_frame(frame)
                        self.is_connected = True
                        self._snapshot_mode = True
                        self._stop_event.clear()
                        self._capture_thread = Thread(target=self._capture_loop, daemon=True)
                        self._capture_thread.start()
                        logger.info("Камера подключена в устойчивом HTTP snapshot режиме")
                        return True

                # Start a bounded retry loop even when the camera is offline at
                # application startup. Do not fall back to blocking RTSP reads.
                self._snapshot_mode = True
                self.is_connected = False
                self._stop_event.clear()
                self._capture_thread = Thread(target=self._capture_loop, daemon=True)
                self._capture_thread.start()
                logger.warning("Камера пока недоступна; запущено фоновое переподключение")
                return True

                urls = [
                    f"rtsp://{self.username}:{self.password}@{self.ip}:554{self.rtsp_path}",
                    f"rtsp://{self.username}:{self.password}@{self.ip}:554/h264",
                    f"rtsp://{self.username}:{self.password}@{self.ip}:554/streaming/channels/1",
                    f"rtsp://{self.username}:{self.password}@{self.ip}:554/Streaming/Channels/101",
                ]

                for url in urls:
                    logger.info(f"Пробуем подключиться к: {url[:60]}...")
                    self.cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
                    if self.cap:
                        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        self.cap.set(cv2.CAP_PROP_FPS, 5)

                    if self.cap and self.cap.isOpened():
                        for _ in range(5):
                            ret, frame = self.cap.read()
                            if ret and frame is not None:
                                self._publish_frame(frame)
                                logger.info(f"✅ Подключено через: {url[:60]}")
                                break
                        else:
                            if self.cap:
                                self.cap.release()
                            self.cap = None
                            continue
                        break
                    else:
                        if self.cap:
                            self.cap.release()
                        self.cap = None

            if not self.cap and self.camera_type in ["usb", "webcam"]:
                self.cap = cv2.VideoCapture(0)
                if self.cap:
                    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

            if not self.cap or not self.cap.isOpened():
                logger.error(f"Не удалось открыть камеру")
                return False

            self.is_connected = True
            logger.info(f"✅ Камера подключена успешно (тип: {self.camera_type})")

            self._stop_event.clear()
            self._capture_thread = Thread(target=self._capture_loop, daemon=True)
            self._capture_thread.start()

            return True

        except Exception as e:
            logger.error(f"Ошибка подключения к камере: {e}")
            return False

    def _capture_loop(self):
        """Цикл захвата кадров"""
        if not CV2_AVAILABLE:
            return

        use_snapshot = self._snapshot_mode

        while not self._stop_event.is_set():
            try:
                if use_snapshot or (self._error_count > 10):
                    use_snapshot = True
                    img_bytes = self.get_snapshot()
                    if img_bytes:
                        nparr = np.frombuffer(img_bytes, np.uint8)
                        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        if frame is not None:
                            self._publish_frame(frame)
                            self._error_count = 0
                            self.is_connected = True
                            time.sleep(0.2)
                            continue

                    self._error_count += 1
                    if self._error_count >= 3:
                        self.is_connected = False
                    time.sleep(min(5, self._error_count))
                    continue

                if self.cap and self.cap.isOpened():
                    # ⭐ ОБЕРНИТЕ В try/except
                    try:
                        ret, frame = self.cap.read()
                        if ret and frame is not None:
                            self._publish_frame(frame)
                            self._error_count = 0
                            time.sleep(0.05)
                        else:
                            self._error_count += 1
                            if self._error_count % 10 == 0:
                                logger.warning(f"Не удалось захватить кадр ({self._error_count} ошибок)")
                            time.sleep(0.1)
                    except Exception as e:
                        # ⭐ ЛОВИМ ЛЮБУЮ ОШИБКУ RTSP
                        logger.debug(f"RTSP ошибка при чтении кадра: {e}")
                        self._error_count += 1
                        if self._error_count > 20:
                            logger.warning("⚠️ Слишком много ошибок RTSP, переключаемся на HTTP снимки")
                            use_snapshot = True
                        time.sleep(0.5)
                else:
                    time.sleep(0.5)

            except Exception as e:
                # ⭐ ГЛАВНЫЙ ПЕРЕХВАТ ОШИБОК
                logger.warning(f"⚠️ Ошибка в цикле захвата: {e}")
                self._error_count += 1
                if self._error_count > 30:
                    logger.error("❌ Критическая ошибка камеры, переключение на HTTP режим")
                    use_snapshot = True
                time.sleep(1)

    def get_frame(self) -> Optional[Dict[str, Any]]:
        """Получить текущий кадр"""
        if not CV2_AVAILABLE or not self.is_connected:
            return None

        with self._frame_lock:
            if self._current_jpeg is None:
                return None
            jpeg_bytes = self._current_jpeg
            width = self._frame_width
            height = self._frame_height
            timestamp = self.frame_timestamp
            sequence = self._frame_sequence
        return {
            "timestamp": timestamp.isoformat() if timestamp else datetime.now().isoformat(),
            "data": jpeg_bytes,
            "size": len(jpeg_bytes),
            "width": width,
            "height": height,
            "sequence_number": sequence,
        }

    def disconnect(self):
        """Отключение от камеры"""
        self._stop_event.set()
        if self._capture_thread:
            self._capture_thread.join(timeout=2)
        if self.cap:
            self.cap.release()
        with self._frame_lock:
            self._current_jpeg = None
        self.is_connected = False
        logger.info("🔌 Камера отключена")
