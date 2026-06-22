
# backend/services/lidar_client.py
import socket
import time
import logging
from typing import Optional, Dict, Any, List
from collections import Counter

logger = logging.getLogger(__name__)

class LidarClient:
    def __init__(self, host: str = "192.168.1.101", port: int = 2111):
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None
        self.is_connected = False
        
        # ═══════════════════════════════════════════════════════════
        #  НАСТРОЙКИ ФИЛЬТРАЦИИ (ОБНОВЛЕНЫ ПО РЕЗУЛЬТАТАМ ТЕСТА)
        # ═══════════════════════════════════════════════════════════
        self.MIN_VALID_DISTANCE = 100    # мм - минимальное реальное расстояние
        self.MAX_VALID_DISTANCE = 3000   # мм - максимальное реальное расстояние
        self.FLOOR_THRESHOLD = 150       # мм - отсечение пола (увеличено для надежности)
        self.MIN_POINTS_FOR_OBJECT = 5   # Минимум точек для объекта
        
        #  ПОРОГИ ОПРЕДЕЛЕНИЯ ПУСТОТЫ (НА ОСНОВЕ ТЕСТА)
        # no_object: 15 точек, empty: 24 точки, filled: 39 точек
        self.EMPTY_POINTS_THRESHOLD = 10   # Если <= 20 точек - пусто
        self.FILLED_POINTS_THRESHOLD = 17 # Если >= 30 точек - заполнено

    def connect(self) -> bool:
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5)
            self.sock.connect((self.host, self.port))
            logger.info(f"✅ Подключен к {self.host}:{self.port}")
            
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
        if not self.sock or not self.is_connected:
            logger.error("Нет соединения")
            return None
        
        try:
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

    def filter_to_70_degrees(self, distances_mm: list) -> list:
        """Оставляет только центральный сектор 70° (от -35° до +35°)"""
        if not distances_mm:
            return []
        
        total = len(distances_mm)
        keep = int(total * 70 / 190)
        if keep % 2 == 0:
            keep -= 1
        
        start = (total - keep) // 2
        end = start + keep
        
        return distances_mm[start:end]

    def parse_scan_data(self, raw_data: str, filter_angle: bool = True, separate_object: bool = True, mode: str = "auto") -> Dict[str, Any]:
        """
        Парсинг данных лидара с ПРАВИЛЬНОЙ ФИЛЬТРАЦИЕЙ
        """
        try:
            if not raw_data:
                return {"error": "Нет данных", "valid": False}
        
            parts = raw_data.split()
        
            result = {
                "valid": True,
                "timestamp": time.time(),
                "distances_mm_raw": [],
                "distances_mm": [],
                "distances_m": [],
                "points_count": 0,
                "is_filtered": False,
                "object_detected": False,
                "floor_level_mm": 0,
                "is_empty": True,
                "empty_confidence": 0,
                "empty_reason": "",
                "object_type": "unknown",
                "object_height_mm": 0
            }
        
            # ═══════════════════════════════════════════════════════════
            # 1. ПАРСИНГ DIST1 С ЖЕСТКОЙ ФИЛЬТРАЦИЕЙ МУСОРА
            # ═══════════════════════════════════════════════════════════
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
                                
                                # ⭐ ЖЕСТКАЯ ФИЛЬТРАЦИЯ:
                                # 1. Только положительные значения
                                # 2. Не слишком маленькие (убираем 0 и шум)
                                # 3. Не слишком большие (убираем мусор > 5000)
                                if 100 < value < 5000:
                                    result["distances_mm_raw"].append(value)
                        except ValueError:
                            pass
                        j += 1
                    break
        
            logger.info(f"📊 Сырых точек (после базовой фильтрации): {len(result['distances_mm_raw'])}")
        
            # ═══════════════════════════════════════════════════════════
            # 2. ФИЛЬТРАЦИЯ УГЛА (70°)
            # ═══════════════════════════════════════════════════════════
            if filter_angle and result["distances_mm_raw"]:
                filtered_angle = self.filter_to_70_degrees(result["distances_mm_raw"])
                logger.info(f"📊 После фильтрации угла: {len(filtered_angle)} точек")
                current_points = filtered_angle
            else:
                current_points = result["distances_mm_raw"]
        
            # ═══════════════════════════════════════════════════════════
            # 3. ФИЛЬТРАЦИЯ ПО РАССТОЯНИЮ (убираем шум)
            # ═══════════════════════════════════════════════════════════
            if current_points:
                valid_points = [d for d in current_points 
                               if self.MIN_VALID_DISTANCE <= d <= self.MAX_VALID_DISTANCE]
                
                if valid_points:
                    logger.info(f"🔍 После фильтрации расстояний: {len(valid_points)} точек")
                    current_points = valid_points
                else:
                    current_points = []
                    logger.warning("⚠️ Нет валидных точек после фильтрации расстояний")
        
            # ═══════════════════════════════════════════════════════════
            # 4. ОТСЕЧЕНИЕ ПОЛА И ДЕТЕКЦИЯ ОБЪЕКТА
            # ═══════════════════════════════════════════════════════════
            if current_points and separate_object:
                # ⭐ УРОВЕНЬ ПОЛА: самое частое значение в ДИАПАЗОНЕ 1500-3000 мм
                # Это исключает мусор и дает реальный пол
                floor_candidates = [d for d in current_points if 1500 <= d <= 3000]
                
                if floor_candidates:
                    counter = Counter(floor_candidates)
                    floor_level = counter.most_common(1)[0][0]
                    logger.info(f"🏗️ Уровень пола (из диапазона 1500-3000): {floor_level} мм")
                else:
                    # Fallback: самое частое значение
                    counter = Counter(current_points)
                    floor_level = counter.most_common(1)[0][0]
                    logger.info(f"🏗️ Уровень пола (fallback): {floor_level} мм")
                
                result["floor_level_mm"] = floor_level
                
                # Отсекаем пол - все что дальше от пола чем порог
                object_points = [d for d in current_points if d < floor_level - self.FLOOR_THRESHOLD]
                
                if object_points:
                    min_dist = min(object_points)
                    object_height = floor_level - min_dist
                    points_count = len(object_points)
                    
                    logger.info(f"📦 Объект: {points_count} точек, высота={object_height} мм")
                    
                    # ═══════════════════════════════════════════════════════════
                    # ⭐ ОПРЕДЕЛЯЕМ ПУСТОТУ ПО НОВЫМ ПОРОГАМ (ИЗ ТЕСТА)
                    # ═══════════════════════════════════════════════════════════
                    if points_count <= self.EMPTY_POINTS_THRESHOLD:
                        is_empty = True
                        confidence = 90
                        reason = f"Мало точек: {points_count} (пусто)"
                        object_type = "empty"
                    elif points_count >= self.FILLED_POINTS_THRESHOLD:
                        is_empty = False
                        confidence = 85
                        reason = f"Много точек: {points_count} (заполнено)"
                        object_type = "box"
                    else:
                        # Промежуточная зона
                        if points_count < 25:
                            is_empty = True
                            confidence = 70
                            reason = f"Промежуточное точек: {points_count} (скорее пусто)"
                            object_type = "empty"
                        else:
                            is_empty = False
                            confidence = 65
                            reason = f"Промежуточное точек: {points_count} (скорее заполнено)"
                            object_type = "box"
                    
                    result["distances_mm"] = object_points
                    result["is_empty"] = is_empty
                    result["empty_confidence"] = confidence
                    result["empty_reason"] = reason
                    result["object_type"] = object_type
                    result["object_height_mm"] = object_height
                    result["object_detected"] = True
                    
                    logger.info(f"✅ Результат: {reason}")
                else:
                    result["distances_mm"] = []
                    result["is_empty"] = True
                    result["empty_confidence"] = 100
                    result["empty_reason"] = "Нет точек объекта (пол)"
                    result["object_type"] = "empty"
                    result["object_detected"] = False
                    logger.info("📭 Объект не обнаружен")
            else:
                result["distances_mm"] = current_points or []
        
            # ═══════════════════════════════════════════════════════════
            # 5. СТАТИСТИКА
            # ═══════════════════════════════════════════════════════════
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
        
            logger.info(f"📊 Итог: точек={result['points_count']}, пусто={result['is_empty']}")
            return result
        
        except Exception as e:
            logger.error(f"Ошибка парсинга: {e}", exc_info=True)
            return {"error": str(e), "valid": False}

    def disconnect(self):
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.is_connected = False
            logger.info("🔌 Отключен")

    def check_if_empty(self, scan_data: Dict) -> Dict:
        from services.empty_detector import EmptyDetector
        return EmptyDetector.is_empty(scan_data)
    
    def get_empty_status(self, scan_data: Dict) -> str:
        from services.empty_detector import EmptyDetector
        result = EmptyDetector.is_empty(scan_data)
        return "empty" if result["is_empty"] else "occupied"


# Глобальный экземпляр
lidar_client = LidarClient()