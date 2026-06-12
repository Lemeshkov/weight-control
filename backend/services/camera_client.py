# backend/services/camera_client.py
import cv2
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import numpy as np
from threading import Thread, Event
import time
import requests

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
        self.cap: Optional[cv2.VideoCapture] = None
        self.is_connected = False
        self.current_frame: Optional[np.ndarray] = None
        self.frame_timestamp: Optional[datetime] = None
        self._stop_event = Event()
        self._capture_thread: Optional[Thread] = None
        self._error_count = 0
        
    def _get_stream_url(self) -> str:
        """Формирует URL для потока"""
        if self.camera_type == "usb":
            return "0"
        elif self.camera_type == "webcam":
            return "0"
        elif self.camera_type == "ip":
            # RTSP URL для Hikvision
            if self.username and self.password:
                # Правильный формат для Hikvision
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
        try:
            url = self._get_snapshot_url()
            response = requests.get(url, timeout=2, auth=(self.username, self.password))
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
        try:
            if self.camera_type == "ip":
                # Пробуем разные варианты RTSP URL
                urls = [
                    f"rtsp://{self.username}:{self.password}@{self.ip}:554{self.rtsp_path}",
                    f"rtsp://{self.username}:{self.password}@{self.ip}:554/h264",
                    f"rtsp://{self.username}:{self.password}@{self.ip}:554/streaming/channels/1",
                    f"rtsp://{self.username}:{self.password}@{self.ip}:554/Streaming/Channels/101",
                ]
                
                for url in urls:
                    logger.info(f"Пробуем подключиться к: {url[:60]}...")
                    self.cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
                    self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Уменьшаем буфер
                    self.cap.set(cv2.CAP_PROP_FPS, 5)  # Ограничиваем FPS
                    
                    if self.cap.isOpened():
                        # Проверяем, что камера работает
                        for _ in range(5):  # Делаем несколько попыток чтения
                            ret, frame = self.cap.read()
                            if ret and frame is not None:
                                self.current_frame = frame
                                self.frame_timestamp = datetime.now()
                                logger.info(f"✅ Подключено через: {url[:60]}")
                                break
                        else:
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
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            
            if not self.cap or not self.cap.isOpened():
                logger.error(f"Не удалось открыть камеру")
                return False
            
            self.is_connected = True
            logger.info(f"✅ Камера подключена успешно (тип: {self.camera_type})")
            
            # Запускаем поток захвата
            self._stop_event.clear()
            self._capture_thread = Thread(target=self._capture_loop, daemon=True)
            self._capture_thread.start()
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка подключения к камере: {e}")
            return False
    
    def _capture_loop(self):
        """Цикл захвата кадров"""
        consecutive_errors = 0
        use_snapshot = False  # Флаг переключения на HTTP снимки
        
        while not self._stop_event.is_set():
            try:
                # Если RTSP не работает, пробуем HTTP snapshot
                if use_snapshot or (self._error_count > 10):
                    use_snapshot = True
                    img_bytes = self.get_snapshot()
                    if img_bytes:
                        # Конвертируем байты в изображение OpenCV
                        import cv2
                        import numpy as np
                        nparr = np.frombuffer(img_bytes, np.uint8)
                        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        if frame is not None:
                            self.current_frame = frame
                            self.frame_timestamp = datetime.now()
                            self._error_count = 0
                            time.sleep(0.5)  # Пауза между снимками
                            continue
                    
                    self._error_count += 1
                    time.sleep(1)
                    continue
                
                # Пробуем RTSP
                if self.cap and self.cap.isOpened():
                    ret, frame = self.cap.read()
                    if ret and frame is not None:
                        self.current_frame = frame
                        self.frame_timestamp = datetime.now()
                        self._error_count = 0
                        time.sleep(0.05)
                    else:
                        self._error_count += 1
                        if self._error_count % 10 == 0:
                            logger.warning(f"Не удалось захватить кадр ({self._error_count} ошибок)")
                        time.sleep(0.1)
                else:
                    time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Ошибка в цикле захвата: {e}")
                time.sleep(1)
    
    def get_frame(self) -> Optional[Dict[str, Any]]:
        """Получить текущий кадр"""
        if not self.is_connected:
            return None
        
        frame = self.current_frame
        if frame is None:
            return None
        
        try:
            # Создаём копию кадра
            frame_copy = frame.copy()
            
            # Оптимизация размера для передачи
            if frame_copy.shape[1] > 1024:
                scale = 1024 / frame_copy.shape[1]
                new_width = int(frame_copy.shape[1] * scale)
                new_height = int(frame_copy.shape[0] * scale)
                frame_copy = cv2.resize(frame_copy, (new_width, new_height))
            
            # Кодируем в JPEG
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 70]
            _, buffer = cv2.imencode('.jpg', frame_copy, encode_param)
            jpeg_bytes = buffer.tobytes()
            
            return {
                "timestamp": self.frame_timestamp.isoformat() if self.frame_timestamp else datetime.now().isoformat(),
                "data": jpeg_bytes,
                "size": len(jpeg_bytes),
                "width": frame_copy.shape[1],
                "height": frame_copy.shape[0]
            }
        except Exception as e:
            logger.error(f"Ошибка получения кадра: {e}")
            return None
    
    def disconnect(self):
        """Отключение от камеры"""
        self._stop_event.set()
        if self._capture_thread:
            self._capture_thread.join(timeout=2)
        if self.cap:
            self.cap.release()
        self.is_connected = False
        logger.info("🔌 Камера отключена")

# # backend/services/camera_client.py
# import cv2
# import logging
# from typing import Optional, Dict, Any
# from datetime import datetime
# import numpy as np
# from threading import Thread, Event
# import base64
# import time

# logger = logging.getLogger(__name__)

# class CameraClient:
#     """Клиент для работы с камерой (поддерживает USB, Webcam, IP cameras)"""
    
#     def __init__(self, 
#                  camera_type: str = "webcam",  # usb, webcam, ip
#                  ip: str = "192.168.0.2",
#                  port: int = 8080,
#                  username: str = "",
#                  password: str = "",
#                  rtsp_path: str = "/stream"):
#         self.camera_type = camera_type
#         self.ip = ip
#         self.port = port
#         self.username = username
#         self.password = password
#         self.rtsp_path = rtsp_path
#         self.cap: Optional[cv2.VideoCapture] = None
#         self.is_connected = False
#         self.current_frame: Optional[np.ndarray] = None
#         self.frame_timestamp: Optional[datetime] = None
#         self._stop_event = Event()
#         self._capture_thread: Optional[Thread] = None
        
#     def _get_stream_url(self) -> str:
#         """Формирует URL для потока"""
#         if self.camera_type == "usb":
#             return "0"
#         elif self.camera_type == "webcam":
#             return "0"
#         elif self.camera_type == "ip":
#             # Пробуем разные варианты RTSP URL
#             if self.username and self.password:
#                 # С авторизацией
#                 urls = [
#                     f"rtsp://{self.username}:{self.password}@{self.ip}:{self.port}{self.rtsp_path}",
#                     f"rtsp://{self.username}:{self.password}@{self.ip}:{self.port}/h264",
#                     f"rtsp://{self.username}:{self.password}@{self.ip}:{self.port}/stream",
#                     f"rtsp://{self.username}:{self.password}@{self.ip}:{self.port}/live"
#                 ]
#             else:
#                 # Без авторизации
#                 urls = [
#                     f"rtsp://{self.ip}:{self.port}{self.rtsp_path}",
#                     f"rtsp://{self.ip}:{self.port}/h264",
#                     f"rtsp://{self.ip}:{self.port}/stream",
#                     f"rtsp://{self.ip}:{self.port}/live"
#                 ]
            
#             # Возвращаем первый URL (будет пробовать в connect)
#             return urls[0]
#         else:
#             return "0"
    
#     def connect(self) -> bool:
#         """Подключение к камере"""
#         try:
#             if self.camera_type == "ip":
#                 # Пробуем разные URL для IP камеры
#                 urls = [
#                     f"rtsp://{self.username}:{self.password}@{self.ip}:{self.port}{self.rtsp_path}" if self.username else f"rtsp://{self.ip}:{self.port}{self.rtsp_path}",
#                     f"rtsp://{self.username}:{self.password}@{self.ip}:{self.port}/h264" if self.username else f"rtsp://{self.ip}:{self.port}/h264",
#                     f"rtsp://{self.username}:{self.password}@{self.ip}:{self.port}/stream" if self.username else f"rtsp://{self.ip}:{self.port}/stream",
#                     f"http://{self.ip}:{self.port}/video",
#                     f"http://{self.ip}:{self.port}/mjpeg"
#                 ]
                
#                 for url in urls:
#                     logger.info(f"Пробуем подключиться к: {url[:50]}...")
#                     self.cap = cv2.VideoCapture(url)
#                     if self.cap.isOpened():
#                         ret, test_frame = self.cap.read()
#                         if ret and test_frame is not None:
#                             logger.info(f"✅ Подключено через: {url[:50]}")
#                             break
#                         else:
#                             self.cap.release()
#                             self.cap = None
#             else:
#                 # Для USB/Webcam камеры
#                 self.cap = cv2.VideoCapture(0)
            
#             if not self.cap or not self.cap.isOpened():
#                 logger.error(f"Не удалось открыть камеру")
#                 return False
            
#             self.is_connected = True
#             logger.info(f"✅ Камера подключена успешно (тип: {self.camera_type})")
            
#             # Запускаем поток захвата
#             self._stop_event.clear()
#             self._capture_thread = Thread(target=self._capture_loop, daemon=True)
#             self._capture_thread.start()
            
#             return True
            
#         except Exception as e:
#             logger.error(f"Ошибка подключения к камере: {e}")
#             return False
    
#     def _capture_loop(self):
#         """Цикл захвата кадров"""
#         frame_count = 0
#         while not self._stop_event.is_set():
#             try:
#                 if self.cap and self.cap.isOpened():
#                     ret, frame = self.cap.read()
#                     if ret and frame is not None:
#                         self.current_frame = frame
#                         self.frame_timestamp = datetime.now()
#                         frame_count += 1
#                         if frame_count % 30 == 0:
#                             logger.debug(f"Захвачено кадров: {frame_count}")
#                     else:
#                         logger.warning("Не удалось захватить кадр")
#                         time.sleep(0.1)
#                 else:
#                     logger.warning("Камера не доступна")
#                     time.sleep(1)
                
#                 time.sleep(0.033)  # ~30 fps
                
#             except Exception as e:
#                 logger.error(f"Ошибка в цикле захвата: {e}")
#                 time.sleep(1)
    
#     def get_frame(self) -> Optional[Dict[str, Any]]:
#         """Получить текущий кадр"""
#         if not self.is_connected or self.current_frame is None:
#             return None
        
#         try:
#             frame = self.current_frame.copy()
            
#             # Оптимизация размера для передачи
#             if frame.shape[1] > 1024:
#                 scale = 1024 / frame.shape[1]
#                 new_width = int(frame.shape[1] * scale)
#                 new_height = int(frame.shape[0] * scale)
#                 frame = cv2.resize(frame, (new_width, new_height))
            
#             # Кодируем в JPEG
#             encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 75]
#             _, buffer = cv2.imencode('.jpg', frame, encode_param)
#             jpeg_bytes = buffer.tobytes()
            
#             return {
#                 "timestamp": self.frame_timestamp.isoformat() if self.frame_timestamp else datetime.now().isoformat(),
#                 "data": jpeg_bytes,
#                 "size": len(jpeg_bytes),
#                 "width": frame.shape[1],
#                 "height": frame.shape[0]
#             }
#         except Exception as e:
#             logger.error(f"Ошибка получения кадра: {e}")
#             return None
    
#     def disconnect(self):
#         """Отключение от камеры"""
#         self._stop_event.set()
#         if self._capture_thread:
#             self._capture_thread.join(timeout=2)
#         if self.cap:
#             self.cap.release()
#         self.is_connected = False
#         logger.info("🔌 Камера отключена")