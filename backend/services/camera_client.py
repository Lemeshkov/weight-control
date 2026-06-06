# backend/services/camera_client.py
import cv2
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import numpy as np
from threading import Thread, Event
import base64
import time

logger = logging.getLogger(__name__)

class CameraClient:
    """Клиент для работы с камерой (поддерживает USB, Webcam, IP cameras)"""
    
    def __init__(self, 
                 camera_type: str = "webcam",  # usb, webcam, ip
                 ip: str = "192.168.0.2",
                 port: int = 8080,
                 username: str = "",
                 password: str = "",
                 rtsp_path: str = "/stream"):
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
        
    def _get_stream_url(self) -> str:
        """Формирует URL для потока"""
        if self.camera_type == "usb":
            return "0"
        elif self.camera_type == "webcam":
            return "0"
        elif self.camera_type == "ip":
            # Пробуем разные варианты RTSP URL
            if self.username and self.password:
                # С авторизацией
                urls = [
                    f"rtsp://{self.username}:{self.password}@{self.ip}:{self.port}{self.rtsp_path}",
                    f"rtsp://{self.username}:{self.password}@{self.ip}:{self.port}/h264",
                    f"rtsp://{self.username}:{self.password}@{self.ip}:{self.port}/stream",
                    f"rtsp://{self.username}:{self.password}@{self.ip}:{self.port}/live"
                ]
            else:
                # Без авторизации
                urls = [
                    f"rtsp://{self.ip}:{self.port}{self.rtsp_path}",
                    f"rtsp://{self.ip}:{self.port}/h264",
                    f"rtsp://{self.ip}:{self.port}/stream",
                    f"rtsp://{self.ip}:{self.port}/live"
                ]
            
            # Возвращаем первый URL (будет пробовать в connect)
            return urls[0]
        else:
            return "0"
    
    def connect(self) -> bool:
        """Подключение к камере"""
        try:
            if self.camera_type == "ip":
                # Пробуем разные URL для IP камеры
                urls = [
                    f"rtsp://{self.username}:{self.password}@{self.ip}:{self.port}{self.rtsp_path}" if self.username else f"rtsp://{self.ip}:{self.port}{self.rtsp_path}",
                    f"rtsp://{self.username}:{self.password}@{self.ip}:{self.port}/h264" if self.username else f"rtsp://{self.ip}:{self.port}/h264",
                    f"rtsp://{self.username}:{self.password}@{self.ip}:{self.port}/stream" if self.username else f"rtsp://{self.ip}:{self.port}/stream",
                    f"http://{self.ip}:{self.port}/video",
                    f"http://{self.ip}:{self.port}/mjpeg"
                ]
                
                for url in urls:
                    logger.info(f"Пробуем подключиться к: {url[:50]}...")
                    self.cap = cv2.VideoCapture(url)
                    if self.cap.isOpened():
                        ret, test_frame = self.cap.read()
                        if ret and test_frame is not None:
                            logger.info(f"✅ Подключено через: {url[:50]}")
                            break
                        else:
                            self.cap.release()
                            self.cap = None
            else:
                # Для USB/Webcam камеры
                self.cap = cv2.VideoCapture(0)
            
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
        frame_count = 0
        while not self._stop_event.is_set():
            try:
                if self.cap and self.cap.isOpened():
                    ret, frame = self.cap.read()
                    if ret and frame is not None:
                        self.current_frame = frame
                        self.frame_timestamp = datetime.now()
                        frame_count += 1
                        if frame_count % 30 == 0:
                            logger.debug(f"Захвачено кадров: {frame_count}")
                    else:
                        logger.warning("Не удалось захватить кадр")
                        time.sleep(0.1)
                else:
                    logger.warning("Камера не доступна")
                    time.sleep(1)
                
                time.sleep(0.033)  # ~30 fps
                
            except Exception as e:
                logger.error(f"Ошибка в цикле захвата: {e}")
                time.sleep(1)
    
    def get_frame(self) -> Optional[Dict[str, Any]]:
        """Получить текущий кадр"""
        if not self.is_connected or self.current_frame is None:
            return None
        
        try:
            frame = self.current_frame.copy()
            
            # Оптимизация размера для передачи
            if frame.shape[1] > 1024:
                scale = 1024 / frame.shape[1]
                new_width = int(frame.shape[1] * scale)
                new_height = int(frame.shape[0] * scale)
                frame = cv2.resize(frame, (new_width, new_height))
            
            # Кодируем в JPEG
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 75]
            _, buffer = cv2.imencode('.jpg', frame, encode_param)
            jpeg_bytes = buffer.tobytes()
            
            return {
                "timestamp": self.frame_timestamp.isoformat() if self.frame_timestamp else datetime.now().isoformat(),
                "data": jpeg_bytes,
                "size": len(jpeg_bytes),
                "width": frame.shape[1],
                "height": frame.shape[0]
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