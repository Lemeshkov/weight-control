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
        
    def get_current_angle_range(self) -> Optional[Dict[str, Any]]:
        """
        Проверить текущие настройки угла сканирования
        Команда: sRN LMPoutputRange
        Ответ: sRA LMPoutputRange 1 +5000 -3500 +3500
        где: +5000 = 0.5° разрешение, -3500 = -35°, +3500 = +35°
        """
        try:
            response = self._send_raw("sRN LMPoutputRange")
            if response and "sRA LMPoutputRange" in response:
                parts = response.split()
                # sRA LMPoutputRange 1 +5000 -3500 +3500
                if len(parts) >= 5:
                    return {
                        "resolution_raw": parts[2],
                        "resolution_deg": int(parts[2]) / 10000,
                        "start_angle_raw": parts[3],
                        "start_angle_deg": int(parts[3]) / 100,
                        "stop_angle_raw": parts[4],
                        "stop_angle_deg": int(parts[4]) / 100,
                        "total_angle_deg": (int(parts[4]) - int(parts[3])) / 100
                    }
            return None
        except Exception as e:
            logger.error(f"Ошибка получения угла: {e}")
            return None

    def _hex_to_signed_int(self, hex_str: str) -> int:
        """Преобразует HEX строку в знаковое целое"""
        try:
            val = int(hex_str, 16)
            # Если это 32-битное число и старший бит = 1, оно отрицательное
            if val > 0x7FFFFFFF:
                val = val - 0x100000000
            return val
        except ValueError:
            return 0

    def filter_to_70_degrees(self, distances_mm: list) -> list:
        """Оставляет только центральный сектор 70° (от -35° до +35°)"""
        if not distances_mm:
            return []
        
        total = len(distances_mm)
        # Полный угол 190°, нужен 70° → оставляем 36.8% точек
        keep = int(total * 70 / 190)
        if keep % 2 == 0:
            keep -= 1
        
        start = (total - keep) // 2
        end = start + keep
        
        logger.info(f"Фильтрация: {total} → {keep} точек (сектор 70°)")
        return distances_mm[start:end]

    def get_current_angle_range_hex(self) -> Optional[Dict[str, Any]]:
        """
        Проверить текущие настройки угла сканирования (HEX версия)
        Ответ: sRA LMPoutputRange 1 1388 FFFF3CB0 1C3A90
        где: 1388 = 5000 (0.5°), FFFF3CB0 = -3500 (-35°), 1C3A90 = 1850000
        """
        try:
            response = self._send_raw("sRN LMPoutputRange")
            if response and "sRA LMPoutputRange" in response:
                parts = response.split()
                # sRA LMPoutputRange 1 1388 FFFF3CB0 1C3A90
                if len(parts) >= 5:
                    resolution_raw = int(parts[2], 16)
                    start_raw = self._hex_to_signed_int(parts[3])
                    stop_raw = self._hex_to_signed_int(parts[4])
                    
                    return {
                        "resolution_raw": hex(resolution_raw),
                        "resolution_deg": resolution_raw / 10000,
                        "start_angle_raw": hex(start_raw & 0xFFFFFFFF) if start_raw < 0 else hex(start_raw),
                        "start_angle_deg": start_raw / 100,
                        "stop_angle_raw": hex(stop_raw),
                        "stop_angle_deg": stop_raw / 100,
                        "total_angle_deg": (stop_raw - start_raw) / 100
                    }
            return None
        except Exception as e:
            logger.error(f"Ошибка получения угла: {e}")
            return None

    def parse_scan_data(self, raw_data: str, filter_angle: bool = True) -> Dict[str, Any]:
        """Парсинг данных лидара с опциональной фильтрацией угла"""
        try:
            if not raw_data:
                return {"error": "Нет данных", "valid": False}
            
            parts = raw_data.split()
            
            result = {
                "valid": True,
                "timestamp": time.time(),
                "distances_mm_raw": [],  # сырые данные
                "distances_mm": [],      # отфильтрованные
                "distances_m": [],
                "points_count": 0,
                "is_filtered": False
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
                                    result["distances_mm_raw"].append(value)
                        except ValueError:
                            pass
                        j += 1
                    break
            
            # Применяем фильтрацию угла (от -35° до +35°)
            if filter_angle and result["distances_mm_raw"]:
                result["distances_mm"] = self.filter_to_70_degrees(result["distances_mm_raw"])
                result["is_filtered"] = True
                logger.info(f"Фильтрация применена: {len(result['distances_mm_raw'])} → {len(result['distances_mm'])} точек")
            else:
                result["distances_mm"] = result["distances_mm_raw"]
            
            # Вычисляем статистику на основе ОТФИЛЬТРОВАННЫХ данных
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