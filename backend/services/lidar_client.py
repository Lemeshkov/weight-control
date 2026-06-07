# backend/services/lidar_client.py
import socket
import time
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class LidarClient:
    def __init__(self, host: str = "192.168.1.101", port: int = 2111):
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None
        self.is_connected = False

    def connect(self) -> bool:
        """Подключение к лидару"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5)
            self.sock.connect((self.host, self.port))
            logger.info(f"✅ Подключен к {self.host}:{self.port}")
            
            # Отправляем команды (как в тестовом скрипте)
            self._send_raw("sMN SetAccessMode 3 F4724744")
            time.sleep(0.2)
            self._send_raw("sMN Run")
            time.sleep(0.2)
            
            self.is_connected = True
            logger.info(f"✅ Лидар готов")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            return False

    def _send_raw(self, cmd: str) -> Optional[str]:
        """Отправка команды и получение ответа (как в тестовом скрипте)"""
        if not self.sock:
            return None
        
        full_cmd = f"\x02{cmd}\x03"
        
        try:
            self.sock.send(full_cmd.encode('utf-8'))
            time.sleep(0.2)
            response = self.sock.recv(65535)
            decoded = response.decode('utf-8', errors='ignore')
            decoded = decoded.strip('\x02\x03')
            return decoded
        except socket.timeout:
            logger.error(f"Таймаут при отправке {cmd}")
            return None
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            return None

    def get_scan_data(self) -> Optional[str]:
        """Получить данные сканирования"""
        if not self.sock or not self.is_connected:
            logger.error("Нет соединения")
            return None
        
        try:
            # Отправляем команду как в тестовом скрипте
            full_cmd = f"\x02sRN LMDscandata\x03"
            self.sock.send(full_cmd.encode('utf-8'))
            time.sleep(0.3)
            response = self.sock.recv(65535)
            decoded = response.decode('utf-8', errors='ignore')
            decoded = decoded.strip('\x02\x03')
            
            if decoded and "sRA LMDscandata" in decoded:
                logger.info(f"✅ Данные получены ({len(decoded)} байт)")
                return decoded
            else:
                logger.warning(f"Неверный ответ: {decoded[:100] if decoded else 'None'}")
                return None
                
        except socket.timeout:
            logger.error("Таймаут при получении данных")
            return None
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            return None

    def parse_scan_data(self, raw_data: str) -> Dict[str, Any]:
        """Парсинг данных лидара"""
        try:
            if not raw_data:
                return {"error": "Нет данных", "valid": False}
            
            parts = raw_data.split()
            
            result = {
                "valid": True,
                "timestamp": time.time(),
                "distances_mm": [],
                "distances_m": [],
                "points_count": 0
            }
            
            # Ищем DIST1
            for i, part in enumerate(parts):
                if part == "DIST1" and i + 1 < len(parts):
                    j = i + 1
                    while j < len(parts) and parts[j] not in ["RSSI1", "RSSI2", "DIST2", "DEVICE"]:
                        try:
                            hex_val = parts[j].strip()
                            if hex_val:
                                value = int(hex_val, 16)
                                if value > 0x7FFFFFFF:
                                    value = value - 0x100000000
                                if 0 <= value <= 50000:
                                    result["distances_mm"].append(value)
                        except ValueError:
                            pass
                        j += 1
                    break
            
            if result["distances_mm"]:
                result["distances_m"] = [round(d/1000, 2) for d in result["distances_mm"]]
                result["points_count"] = len(result["distances_mm"])
                
                valid_dist = [d for d in result["distances_mm"] if 0 < d < 50000]
                if valid_dist:
                    result["min_distance_mm"] = min(valid_dist)
                    result["max_distance_mm"] = max(valid_dist)
                    result["avg_distance_mm"] = sum(valid_dist) // len(valid_dist)
                    result["min_distance_m"] = round(min(valid_dist)/1000, 2)
                    result["max_distance_m"] = round(max(valid_dist)/1000, 2)
                    result["avg_distance_m"] = round(sum(valid_dist)/len(valid_dist)/1000, 2)
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка парсинга: {e}")
            return {"error": str(e), "valid": False}

    def disconnect(self):
        """Отключение"""
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.is_connected = False
            logger.info("🔌 Отключен")
