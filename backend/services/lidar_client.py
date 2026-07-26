# backend/services/lidar_client.py

import socket
import time
import logging
import json
import os
from typing import Optional, Dict, Any, List
from collections import Counter, deque
from services.object_detector import ObjectDetector

logger = logging.getLogger(__name__)

class LidarClient:
    def __init__(self, host: str = "192.168.1.101", port: int = 2111):
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None
        self.is_connected = False

        # ═══════════════════════════════════════════════════════════
        # ПРАВИЛЬНЫЕ НАСТРОЙКИ (ФИЗИЧЕСКАЯ КАРТИНА)
        # ═══════════════════════════════════════════════════════════
        self.MIN_VALID_DISTANCE = 100    # мм - отбрасываем провод на 1м
        self.MAX_VALID_DISTANCE = 3000    # мм - пол на 2742 мм
        self.FLOOR_LEVEL = self._load_floor_level()
        self.FLOOR_THRESHOLD = 150          # мм - отсечение пола

        # ПОРОГИ ДЛЯ ОПРЕДЕЛЕНИЯ ПУСТОТЫ
        self.EMPTY_POINTS_THRESHOLD = 10   # Если <= 10 точек - пусто
        self.FILLED_POINTS_THRESHOLD = 15  # Если >= 15 точек - заполнено
        self.MIN_OBJECT_POINTS = 1

        # БУФЕР ДЛЯ СТАБИЛИЗАЦИИ
        self.scan_buffer = deque(maxlen=3)
        self.stable_points = []

    def _load_floor_level(self) -> int:
        """Загрузить уровень пола, сохранённый calibrate_floor.py."""
        default_level = 2742
        config_path = os.getenv(
            "FLOOR_CONFIG_PATH",
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "floor_config.json")
        )

        try:
            with open(config_path, "r", encoding="utf-8") as config_file:
                config = json.load(config_file)
            floor_level = int(round(float(config["floor_level_mm"])))
            if not self.MIN_VALID_DISTANCE < floor_level <= 10000:
                raise ValueError(f"floor_level_mm вне допустимого диапазона: {floor_level}")
            logger.info("Загружен калиброванный уровень пола: %s мм (%s)", floor_level, config_path)
            return floor_level
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            logger.warning(
                "Не удалось загрузить калибровку пола из %s: %s. "
                "Используется значение по умолчанию %s мм",
                config_path, exc, default_level,
            )
            return default_level

    def connect(self) -> bool:
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5)
            self.sock.connect((self.host, self.port))
            logger.info(f"✅ Подключен к {self.host}:{self.port}")

            # АВТОРИЗАЦИЯ (ОБЯЗАТЕЛЬНО!)
            self._send_raw("sMN SetAccessMode 3 F4724744")
            time.sleep(0.2)
            self._send_raw("sMN Run")
            time.sleep(0.2)

            self.is_connected = True
            logger.info(f"✅ Лидар готов")
            logger.info(f"📐 Настройки фильтрации:")
            logger.info(f"   MIN_VALID_DISTANCE = {self.MIN_VALID_DISTANCE} мм (отбрасываем провод)")
            logger.info(f"   MAX_VALID_DISTANCE = {self.MAX_VALID_DISTANCE} мм (пол)")
            logger.info(f"   FLOOR_LEVEL = {self.FLOOR_LEVEL} мм (реальный пол)")
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

    def get_current_angle_range(self) -> Optional[Dict[str, Any]]:
        try:
            response = self._send_raw("sRN LMPoutputRange")
            if response and "sRA LMPoutputRange" in response:
                parts = response.split()
                if len(parts) >= 6:
                    resolution_raw = int(parts[3], 16)
                    start_raw = self._hex_to_signed_int(parts[4])
                    stop_raw = self._hex_to_signed_int(parts[5])

                    return {
                        "resolution_raw": parts[3],
                        "resolution_deg": resolution_raw / 10000,
                        "start_angle_raw": parts[4],
                        "start_angle_deg": start_raw / 10000,
                        "stop_angle_raw": parts[5],
                        "stop_angle_deg": stop_raw / 10000,
                        "total_angle_deg": (stop_raw - start_raw) / 10000
                    }
            return None
        except Exception as e:
            logger.error(f"Ошибка получения угла: {e}")
            return None

    def _hex_to_signed_int(self, hex_str: str) -> int:
        try:
            val = int(hex_str, 16)
            if val > 0x7FFFFFFF:
                val = val - 0x100000000
            return val
        except ValueError:
            return 0

    def filter_angle(self, distances_mm: list, angle_deg: int = 70) -> list:
        if not distances_mm:
            return []

        total = len(distances_mm)
        keep = int(total * angle_deg / 190)
        if keep % 2 == 0:
            keep -= 1

        start = (total - keep) // 2
        end = start + keep

        return distances_mm[start:end]

    def parse_raw_data(self, raw_data: str) -> List[int]:
        try:
            if not raw_data:
                return []

            parts = raw_data.split()
            distances = []

            for i, part in enumerate(parts):
                # DIST1 is followed by scale, offset, start angle, angular
                # step and point count. Only the subsequent values are ranges.
                if part == "DIST1" and i + 5 < len(parts):
                    points_count = int(parts[i + 5], 16)
                    data_start = i + 6
                    data_end = min(data_start + points_count, len(parts))

                    for j in range(data_start, data_end):
                        try:
                            hex_val = parts[j].strip()
                            if hex_val:
                                value = int(hex_val, 16)
                                if value > 0x7FFFFFFF:
                                    value = value - 0x100000000
                                if self.MIN_VALID_DISTANCE <= value <= self.MAX_VALID_DISTANCE:
                                    distances.append(value)
                        except ValueError:
                            pass
                    break

            return distances

        except Exception as e:
            logger.error(f"Ошибка парсинга: {e}")
            return []

    def get_scan_geometry(self, raw_data: str) -> Dict[str, Any]:
        """Read angular geometry directly from DIST1 metadata."""
        try:
            parts = raw_data.split()
            index = parts.index("DIST1")
            start_angle = self._hex_to_signed_int(parts[index + 3]) / 10000
            angular_step = int(parts[index + 4], 16) / 10000
            points_count = int(parts[index + 5], 16)
            total_angle = max(points_count - 1, 0) * angular_step
            return {
                "start_angle_deg": start_angle,
                "stop_angle_deg": start_angle + total_angle,
                "angular_step_deg": angular_step,
                "points_count": points_count,
                "total_angle_deg": total_angle,
                "source": "DIST1",
            }
        except (ValueError, IndexError):
            return {
                "start_angle_deg": -5.0,
                "stop_angle_deg": 185.0,
                "angular_step_deg": 0.5,
                "points_count": 0,
                "total_angle_deg": 190.0,
                "source": "fallback",
            }

    def filter_valid_distances(self, distances_mm: List[int]) -> List[int]:
        return [d for d in distances_mm
                if self.MIN_VALID_DISTANCE <= d <= self.MAX_VALID_DISTANCE]

    def _filter_floor(self, distances_mm: List[int]) -> List[int]:
        if not distances_mm:
            return []

        object_points = [d for d in distances_mm
                        if d < self.FLOOR_LEVEL - self.FLOOR_THRESHOLD]
        return object_points

    def analyze_scan_with_angles(self, distances_mm: List[int]) -> Dict[str, Any]:
        """
        Анализирует сканирование с учетом углов.
        Ищет объект в диапазоне 1000-2742 мм.
        """
        OBJECT_THRESHOLD = 80

        if not distances_mm or len(distances_mm) < 10:
            return {
                "object_points": [],
                "background_points": [],
                "background_level": self.FLOOR_LEVEL,
                "is_empty": True,
                "points_count": 0,
                "reason": "Нет данных",
                "object_height_mm": 0
            }

        start_angle_deg = -35
        stop_angle_deg = 35
        total_angle = stop_angle_deg - start_angle_deg
        angle_step = total_angle / len(distances_mm) if distances_mm else 0

        points_with_angles = []
        for i, dist in enumerate(distances_mm):
            angle = start_angle_deg + i * angle_step
            points_with_angles.append({
                "index": i,
                "distance": dist,
                "angle": angle
            })

        # Калиброванный пол нельзя заменять доминирующей поверхностью текущего
        # скана: большой кузов или груз часто сам занимает модальный диапазон.
        object_range_points = [
            p for p in points_with_angles
            if self.MIN_VALID_DISTANCE <= p["distance"] <= self.FLOOR_LEVEL + self.FLOOR_THRESHOLD
        ]

        logger.info(
            "После фильтрации по диапазону: %s точек (%s-%s мм)",
            len(object_range_points),
            self.MIN_VALID_DISTANCE,
            self.FLOOR_LEVEL + self.FLOOR_THRESHOLD,
        )

        if len(object_range_points) < 10:
            return {
                "object_points": [],
                "background_points": [],
                "background_level": self.FLOOR_LEVEL,
                "is_empty": True,
                "points_count": 0,
                "reason": f"Мало точек в диапазоне объекта: {len(object_range_points)}",
                "object_height_mm": 0
            }

        points_with_angles = object_range_points

        background_level = self.FLOOR_LEVEL
        background_points = [
            p for p in points_with_angles
            if abs(p["distance"] - background_level) <= OBJECT_THRESHOLD
        ]

        object_candidates = []
        for p in points_with_angles:
            if p["distance"] < background_level - OBJECT_THRESHOLD:
                object_candidates.append(p)

        logger.info(f"🎯 Кандидатов в объект (ближе фона): {len(object_candidates)} точек")

        object_points = []

        if len(object_candidates) >= 1:
            object_candidates.sort(key=lambda x: x["index"])

            clusters = []
            current_cluster = [object_candidates[0]]

            for i in range(1, len(object_candidates)):
                if object_candidates[i]["index"] - object_candidates[i-1]["index"] <= 3:
                    current_cluster.append(object_candidates[i])
                else:
                    clusters.append(current_cluster)
                    current_cluster = [object_candidates[i]]

            if current_cluster:
                clusters.append(current_cluster)

            if clusters:
                best_cluster = max(clusters, key=len)
                object_points = [p["distance"] for p in best_cluster]
                logger.info(f"📦 Кластер объекта: {len(object_points)} точек")

        points_count = len(object_points)

        if points_count < 1:
            is_empty = True
            reason = "Нет точек объекта"
            object_points = []
        elif points_count <= self.EMPTY_POINTS_THRESHOLD:
            is_empty = True
            reason = f"Точек {points_count} <= {self.EMPTY_POINTS_THRESHOLD} (пусто)"
        elif points_count >= self.FILLED_POINTS_THRESHOLD:
            is_empty = False
            reason = f"Точек {points_count} >= {self.FILLED_POINTS_THRESHOLD} (заполнено)"
        else:
            if points_count < 15:
                is_empty = True
                reason = f"Точек {points_count} в промежуточной зоне (скорее пусто)"
            else:
                is_empty = False
                reason = f"Точек {points_count} в промежуточной зоне (скорее заполнено)"

        if object_points:
            min_dist = min(object_points)
            object_height = background_level - min_dist
        else:
            object_height = 0

        logger.info(f"✅ Результат: {'ПУСТО' if is_empty else 'ЗАПОЛНЕН'} ({points_count} точек), высота={object_height}мм")

        return {
            "object_points": object_points,
            "background_points": [p["distance"] for p in background_points],
            "background_level": background_level,
            "is_empty": is_empty,
            "points_count": points_count,
            "reason": reason,
            "object_height_mm": object_height
        }

    def parse_scan_data(self, raw_data: str, filter_angle: bool = True, separate_object: bool = True, mode: str = "auto") -> Dict[str, Any]:
        try:
            if not raw_data:
                return {"error": "Нет данных", "valid": False}

            raw_distances = self.parse_raw_data(raw_data)

            result = {
                "valid": True,
                "timestamp": time.time(),
                "distances_mm_raw": raw_distances,
                "distances_mm": [],
                "distances_m": [],
                "points_count": 0,
                "is_filtered": False,
                "object_detected": False,
                "floor_level_mm": self.FLOOR_LEVEL,
                "is_empty": True,
                "empty_confidence": 0,
                "empty_reason": "",
                "object_type": "unknown",
                "object_height_mm": 0,
                "spread_mm": 0,
                "box_info": {}
            }

            result["scan_geometry"] = self.get_scan_geometry(raw_data)

            logger.info(f" Сырых точек: {len(raw_distances)}")

            if filter_angle and raw_distances:
                filtered_angle = self.filter_angle(raw_distances, 70)
                logger.info(f" После фильтрации угла: {len(filtered_angle)} точек")
                current_points = filtered_angle
            else:
                current_points = raw_distances

            if current_points:
                valid_points = [d for d in current_points
                                if self.MIN_VALID_DISTANCE <= d <= self.MAX_VALID_DISTANCE]
                logger.info(f"🔍 После фильтрации шума: {len(valid_points)} точек")
                current_points = valid_points

            if current_points and separate_object:
                analysis = self.analyze_scan_with_angles(current_points)

                object_points = analysis.get("object_points", [])
                background_level = analysis.get("background_level", self.FLOOR_LEVEL)
                is_empty = analysis.get("is_empty", True)
                reason = analysis.get("reason", "")

                logger.info(f"📊 Анализ с углами завершен:")
                logger.info(f"   Объект: {len(object_points)} точек")
                logger.info(f"   Фон: {background_level} мм")
                logger.info(f"   Статус: {'ПУСТО' if is_empty else 'ЗАПОЛНЕН'}")

                if object_points and len(object_points) >= 1:
                    min_dist = min(object_points)
                    max_dist = max(object_points)
                    object_height = background_level - min_dist
                    spread = max_dist - min_dist

                    result["object_detected"] = True
                    result["distances_mm"] = object_points
                    result["points_count"] = len(object_points)
                    result["floor_level_mm"] = self.FLOOR_LEVEL
                    result["is_empty"] = is_empty
                    result["empty_reason"] = reason
                    result["object_height_mm"] = object_height
                    result["spread_mm"] = spread

                    if is_empty:
                        result["empty_confidence"] = 90
                    else:
                        result["empty_confidence"] = 85

                    if mode == "auto":
                        if len(object_points) < 50:
                            detection_mode = "test_box"
                            logger.info("Автоопределение: режим TEST_BOX")
                        else:
                            detection_mode = "truck"
                            logger.info("Автоопределение: режим TRUCK")
                    else:
                        detection_mode = mode

                    detection_result = ObjectDetector.process_scan(
                        object_points,
                        {"mode": detection_mode, "floor_level": self.FLOOR_LEVEL}
                    )

                    result["object_type"] = detection_result.get("object_type", "box")

                    box_info = detection_result.get("box_info", {})
                    if box_info.get("detected"):
                        result["box_info"] = box_info
                        logger.info(f"📦 Определен тип коробки: {box_info.get('box_label', '?')}")

                    profile = detection_result.get("profile")
                    if profile:
                        result["profile"] = profile
                        result["profile_confidence"] = detection_result.get("profile_confidence", 0)

                    logger.info(f"✅ ObjectDetector: {result['object_type']}, пусто={result['is_empty']}, точек={result['points_count']}")

                else:
                    result["object_detected"] = False
                    result["distances_mm"] = []
                    result["points_count"] = 0
                    result["is_empty"] = True
                    result["empty_confidence"] = 95
                    result["empty_reason"] = "Объект не обнаружен"
                    result["object_type"] = "none"
                    result["object_height_mm"] = 0
                    result["spread_mm"] = 0
                    result["floor_level_mm"] = self.FLOOR_LEVEL
                    result["box_info"] = {}

                    logger.info(f"📭 Объект не обнаружен")
            else:
                result["distances_mm"] = current_points or []
                result["points_count"] = len(result["distances_mm"])
                if result["points_count"] == 0:
                    result["is_empty"] = True
                    result["empty_reason"] = "Нет данных"

            if result["distances_mm"]:
                result["distances_m"] = [round(d/1000, 2) for d in result["distances_mm"]]

                valid_dist = [d for d in result["distances_mm"] if 0 < d < 50000]
                if valid_dist:
                    result["min_distance_mm"] = min(valid_dist)
                    result["max_distance_mm"] = max(valid_dist)
                    result["avg_distance_mm"] = sum(valid_dist) // len(valid_dist)
                    result["min_distance_m"] = round(min(valid_dist)/1000, 2)
                    result["max_distance_m"] = round(max(valid_dist)/1000, 2)
                    result["avg_distance_m"] = round(sum(valid_dist)/len(valid_dist)/1000, 2)

            logger.info(f"📊 Итог: точек={result['points_count']}, пусто={result['is_empty']}, тип={result['object_type']}")
            return result

        except Exception as e:
            logger.error(f"Ошибка парсинга: {e}", exc_info=True)
            return {"error": str(e), "valid": False}

    def calculate_volume(self, distances_mm: List[int], floor_level_mm: int, box_profile, coal_density: float = 850, calibration_factor: float = 1.0) -> Dict[str, float]:
        if not distances_mm or len(distances_mm) < 3:
            return {
                "volume_m3": 0,
                "mass_tons": 0,
                "height_mm": 0,
                "fill_percent": 0,
                "cross_section_m2": 0,
                "points_used": 0,
                "raw_volume_m3": 0,
                "calibration_factor": calibration_factor
            }

        box_width_m = box_profile.width_m
        box_depth_m = box_profile.length_m
        box_height_mm = box_profile.height_m * 1000

        heights_mm = []
        for d in distances_mm:
            height = floor_level_mm - d
            if height > 10:
                heights_mm.append(height)

        if not heights_mm:
            return {
                "volume_m3": 0,
                "mass_tons": 0,
                "height_mm": 0,
                "fill_percent": 0,
                "cross_section_m2": 0,
                "points_used": 0,
                "raw_volume_m3": 0,
                "calibration_factor": calibration_factor
            }

        sorted_heights = sorted(heights_mm)
        trim_count = int(len(sorted_heights) * 0.1)
        if trim_count > 0:
            trimmed_heights = sorted_heights[trim_count:-trim_count]
        else:
            trimmed_heights = sorted_heights

        avg_height_mm = sum(trimmed_heights) / len(trimmed_heights) if trimmed_heights else 0
        avg_height_m = avg_height_mm / 1000

        cross_section_m2 = box_width_m * avg_height_m
        raw_volume_m3 = cross_section_m2 * box_depth_m
        volume_m3 = raw_volume_m3 * calibration_factor

        fill_percent = (avg_height_mm / box_height_mm) * 100 if box_height_mm > 0 else 0
        fill_percent = min(100, max(0, fill_percent))

        mass_tons = (volume_m3 * coal_density) / 1000

        logger.info(f"📐 РАСЧЕТ ОБЪЕМА:")
        logger.info(f"   Средняя высота: {avg_height_mm:.1f} мм ({avg_height_m:.3f} м)")
        logger.info(f"   Ширина: {box_width_m:.2f} м, Глубина: {box_depth_m:.2f} м")
        logger.info(f"   RAW объем: {raw_volume_m3:.4f} м³")
        logger.info(f"   Объем: {volume_m3:.4f} м³, Масса: {mass_tons:.3f} т ({fill_percent:.1f}%)")

        return {
            "volume_m3": round(volume_m3, 4),
            "mass_tons": round(mass_tons, 3),
            "height_mm": round(avg_height_mm, 1),
            "height_m": round(avg_height_m, 3),
            "fill_percent": round(fill_percent, 1),
            "cross_section_m2": round(cross_section_m2, 4),
            "points_used": len(trimmed_heights),
            "raw_volume_m3": round(raw_volume_m3, 4),
            "calibration_factor": calibration_factor
        }

    def disconnect(self):
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.is_connected = False
            logger.info("🔌 Отключен")

    def check_if_empty(self, scan_data: Dict) -> Dict:
        return ObjectDetector.process_scan(scan_data.get("distances_mm", []))

# Глобальный экземпляр
lidar_client = LidarClient()

# # backend/services/lidar_client.py

# import socket
# import time
# import logging
import json
import os
# from typing import Optional, Dict, Any, List
# from collections import Counter, deque
# from services.object_detector import ObjectDetector

# logger = logging.getLogger(__name__)

# class LidarClient:
#     def __init__(self, host: str = "192.168.1.101", port: int = 2111):
#         self.host = host
#         self.port = port
#         self.sock: Optional[socket.socket] = None
#         self.is_connected = False

#         # ═══════════════════════════════════════════════════════════
#         # НАСТРОЙКИ ФИЛЬТРАЦИИ (СОГЛАСНО ФИЗИЧЕСКОЙ КАРТИНЕ)
#         # ═══════════════════════════════════════════════════════════

#         #  ДИАПАЗОНЫ РАССТОЯНИЙ
#         self.MIN_VALID_DISTANCE = 1000     # мм - игнорируем шум/мусор (0-1000мм)
#         self.MAX_VALID_DISTANCE = 2742     # мм - максимальное расстояние объекта
#         self.FLOOR_LEVEL = 2792            # мм - ФИКСИРОВАННЫЙ УРОВЕНЬ ПОЛА
#         self.FLOOR_THRESHOLD = 50          # мм - порог отсечения пола (2742-2792)

#         #  ИСПОЛЬЗУЕМ ФИКСИРОВАННЫЙ ПОЛ
#         self.USE_FIXED_FLOOR = True
#         self.FIXED_FLOOR_LEVEL = 2792      # мм - фиксированный пол

#         #  ПОРОГИ ДЛЯ ОПРЕДЕЛЕНИЯ ПУСТОТЫ
#         self.EMPTY_POINTS_THRESHOLD = 10   # Если <= 10 точек - пусто
#         self.FILLED_POINTS_THRESHOLD = 15  # Если >= 18 точек - заполнено
#         self.MIN_OBJECT_POINTS = 1

#         #  БУФЕР ДЛЯ СТАБИЛИЗАЦИИ
#         self.scan_buffer = deque(maxlen=3)
#         self.stable_points = []



#     def connect(self) -> bool:
#         try:
#             self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#             self.sock.settimeout(5)
#             self.sock.connect((self.host, self.port))
#             logger.info(f"✅ Подключен к {self.host}:{self.port}")

#             # Авторизация
#             # self._send_raw("sMN SetAccessMode 3 F4724744")
#             # time.sleep(0.2)

#             # ⭐ НЕ ЗАПУСКАЕМ СКАНИРОВАНИЕ ЗДЕСЬ!
#             # self._send_raw("sMN Run")  # ← УБИРАЕМ!
#             # time.sleep(0.2)

#             self.is_connected = True
#             logger.info(f"✅ Лидар подключен (угол будет настроен отдельно)")
#             return True

#         except Exception as e:
#             logger.error(f"❌ Ошибка подключения: {e}")
#             return False



#     def _send_raw(self, cmd: str) -> Optional[str]:
#         if not self.sock:
#             return None

#         full_cmd = f"\x02{cmd}\x03"

#         try:
#             self.sock.send(full_cmd.encode('utf-8'))
#             time.sleep(0.2)
#             response = self.sock.recv(65535)
#             decoded = response.decode('utf-8', errors='ignore')
#             decoded = decoded.strip('\x02\x03')
#             return decoded
#         except socket.timeout:
#             logger.error(f"Таймаут при отправке {cmd}")
#             return None
#         except Exception as e:
#             logger.error(f"Ошибка: {e}")
#             return None

#     def get_scan_data(self) -> Optional[str]:
#         if not self.sock or not self.is_connected:
#             logger.error("Нет соединения")
#             return None

#         try:
#             full_cmd = f"\x02sRN LMDscandata\x03"
#             self.sock.send(full_cmd.encode('utf-8'))
#             time.sleep(0.3)
#             response = self.sock.recv(65535)
#             decoded = response.decode('utf-8', errors='ignore')
#             decoded = decoded.strip('\x02\x03')

#             if decoded and "sRA LMDscandata" in decoded:
#                 logger.info(f"✅ Данные получены ({len(decoded)} байт)")
#                 return decoded
#             else:
#                 logger.warning(f"Неверный ответ: {decoded[:100] if decoded else 'None'}")
#                 return None

#         except socket.timeout:
#             logger.error("Таймаут при получении данных")
#             return None
#         except Exception as e:
#             logger.error(f"Ошибка: {e}")
#             return None
        
    
#     def get_current_angle_range(self) -> Optional[Dict[str, Any]]:
#         try:
#             response = self._send_raw("sRN LMPoutputRange")
#             if response and "sRA LMPoutputRange" in response:
#                 parts = response.split()
#                 if len(parts) >= 6:
#                     resolution_raw = int(parts[3], 16)

#                     # Парсим начальный угол
#                     try:
#                         start_raw = int(parts[4])
#                     except ValueError:
#                         start_raw = int(parts[4], 16)
#                         if start_raw > 0x7FFFFFFF:
#                             start_raw = start_raw - 0x100000000

#                     # Парсим конечный угол
#                     try:
#                         stop_raw = int(parts[5])
#                     except ValueError:
#                         stop_raw = int(parts[5], 16)
#                         if stop_raw > 0x7FFFFFFF:
#                             stop_raw = stop_raw - 0x100000000

#                     # ⭐ ПРАВИЛЬНОЕ ДЕЛЕНИЕ НА 10000 (НЕ НА 100!)
#                     return {
#                         "resolution_raw": parts[3],
#                         "resolution_deg": resolution_raw / 10000,
#                         "start_angle_raw": parts[4],
#                         "start_angle_deg": start_raw / 10000,  # ← ИСПРАВЛЕНО
#                         "stop_angle_raw": parts[5],
#                         "stop_angle_deg": stop_raw / 10000,    # ← ИСПРАВЛЕНО
#                         "total_angle_deg": (stop_raw - start_raw) / 1000000  # ← ИСПРАВЛЕНО
#                     }
#         except Exception as e:
#             logger.error(f"Ошибка получения угла: {e}")
#             return None
        

#     def _hex_to_signed_int(self, hex_str: str) -> int:
#         try:
#             val = int(hex_str, 16)
#             if val > 0x7FFFFFFF:
#                 val = val - 0x100000000
#             return val
#         except ValueError:
#             return 0

#     def filter_angle(self, distances_mm: list, angle_deg: int = 30) -> list:
#         if not distances_mm:
#             return []

#         total = len(distances_mm)
#         keep = int(total * angle_deg / 190)
#         if keep % 2 == 0:
#             keep -= 1

#         start = (total - keep) // 2
#         end = start + keep

#         return distances_mm[start:end]
    
#     def parse_raw_data(self, raw_data: str) -> List[int]:
#         try:
#             if not raw_data:
#                 return []

#             parts = raw_data.split()
#             distances = []

#             for i, part in enumerate(parts):
#                 if part == "DIST1" and i + 1 < len(parts):
#                     j = i + 1
#                     skip_count = 0
#                     while j < len(parts) and skip_count < 4:
#                         j += 1
#                         skip_count += 1

#                     while j < len(parts) and parts[j] not in ["RSSI1", "RSSI2", "DIST2", "DEVICE"]:
#                         try:
#                             hex_val = parts[j].strip()
#                             if hex_val:
#                                 value = int(hex_val, 16)
#                                 if value > 0x7FFFFFFF:
#                                     value = value - 0x100000000

#                                 # ⭐ ТОЛЬКО ПАРСИНГ! БЕЗ СМЕЩЕНИЯ!
#                                 if self.MIN_VALID_DISTANCE < value < 50000:
#                                     distances.append(value)
#                         except ValueError:
#                             pass
#                         j += 1
#                     break

#             return distances

#         except Exception as e:
#             logger.error(f"Ошибка парсинга: {e}")
#             return []

  
#     def filter_valid_distances(self, distances_mm: List[int]) -> List[int]:
#         """
#         Фильтрация по валидным расстояниям
#         Используем MIN_VALID_DISTANCE и MAX_VALID_DISTANCE
#         """
#         return [d for d in distances_mm
#                 if self.MIN_VALID_DISTANCE <= d <= self.MAX_VALID_DISTANCE]

#     def _filter_floor(self, distances_mm: List[int]) -> List[int]:
#         """
#         Отсечение пола - оставляем только точки объекта (1000-2742мм)
#         Пол: 2742-2792мм
#         """
#         if not distances_mm:
#             return []

#         # ⭐ Оставляем только точки объекта (не пол)
#         object_points = [d for d in distances_mm
#                         if d < self.FLOOR_LEVEL - self.FLOOR_THRESHOLD]

#         return object_points

#     def _smooth_points(self, points: List[int]) -> List[int]:
#         """
#         Сглаживание точек методом скользящего среднего
#         """
#         if len(points) < 3:
#             return points

#         smoothed = []
#         window_size = 3

#         for i in range(len(points)):
#             start = max(0, i - window_size // 2)
#             end = min(len(points), i + window_size // 2 + 1)
#             window = points[start:end]
#             smoothed.append(int(sum(window) / len(window)))

#         return smoothed
    
#     def analyze_scan_with_angles(self, distances_mm: List[int]) -> Dict[str, Any]:
#         """
#         Анализирует сканирование с учетом углов.
#         Ищет объект в диапазоне 1000-2742 мм (ближе к лидару, чем пол).
#         """
#         OBJECT_MIN_DISTANCE = 1000   # мм - минимальное расстояние объекта
#         OBJECT_MAX_DISTANCE = 2742   # мм - максимальное расстояние объекта (до пола)
#         OBJECT_THRESHOLD = 80        # мм - порог отличия от фона

#         if not distances_mm or len(distances_mm) < 10:
#             return {
#                 "object_points": [],
#                 "background_points": [],
#                 "background_level": self.FLOOR_LEVEL,
#                 "is_empty": True,
#                 "points_count": 0,
#                 "reason": "Нет данных",
#                 "object_height_mm": 0
#             }

#         # ═══════════════════════════════════════════════════════════
#         # 1. ВЫЧИСЛЯЕМ УГЛЫ ДЛЯ КАЖДОЙ ТОЧКИ
#         # ═══════════════════════════════════════════════════════════
#         start_angle_deg = -35
#         stop_angle_deg = 35
#         total_angle = stop_angle_deg - start_angle_deg
#         angle_step = total_angle / len(distances_mm) if distances_mm else 0

#         points_with_angles = []
#         for i, dist in enumerate(distances_mm):
#             angle = start_angle_deg + i * angle_step
#             points_with_angles.append({
#                 "index": i,
#                 "distance": dist,
#                 "angle": angle
#             })

#         # ═══════════════════════════════════════════════════════════
#         # 2. ФИЛЬТРАЦИЯ ПО ДИАПАЗОНУ ОБЪЕКТА (1000-2742 мм)
#         # ═══════════════════════════════════════════════════════════
#         object_range_points = [p for p in points_with_angles
#                                 if OBJECT_MIN_DISTANCE <= p["distance"] <= OBJECT_MAX_DISTANCE]

#         logger.info(f"📊 После фильтрации по диапазону: {len(object_range_points)} точек (1000-2742мм)")

#         if len(object_range_points) < 10:
#             return {
#                 "object_points": [],
#                 "background_points": [],
#                 "background_level": self.FLOOR_LEVEL,
#                 "is_empty": True,
#                 "points_count": 0,
#                 "reason": f"Мало точек в диапазоне объекта: {len(object_range_points)}",
#                 "object_height_mm": 0
#             }

#         points_with_angles = object_range_points

#         # ═══════════════════════════════════════════════════════════
#         # 3. СТРОИМ ГИСТОГРАММУ
#         # ═══════════════════════════════════════════════════════════
#         bins = {}
#         for p in points_with_angles:
#             bin_key = int(p["distance"] / 50) * 50
#             if bin_key not in bins:
#                 bins[bin_key] = []
#             bins[bin_key].append(p)

#         if bins:
#             sorted_bins = sorted(bins.items(), key=lambda x: len(x[1]), reverse=True)
#             background_bin = sorted_bins[0]
#             background_level = background_bin[0]
#             background_points = background_bin[1]

#             logger.info(f"📊 Гистограмма: топ-3 бина")
#             for i, (bin_val, pts) in enumerate(sorted_bins[:3]):
#                 logger.info(f"   #{i+1}: {bin_val} мм -> {len(pts)} точек")
#         else:
#             background_level = self.FLOOR_LEVEL
#             background_points = []

#         # ═══════════════════════════════════════════════════════════
#         # 4. ИЩЕМ ОБЪЕКТ - ТОЧКИ БЛИЖЕ К ЛИДАРУ
#         # ═══════════════════════════════════════════════════════════
#         object_candidates = []
#         for p in points_with_angles:
#             if p["distance"] < background_level - OBJECT_THRESHOLD:
#                 object_candidates.append(p)

#         logger.info(f"🎯 Кандидатов в объект (ближе фона): {len(object_candidates)} точек")

#         # ═══════════════════════════════════════════════════════════
#         # 5. ИЩЕМ КЛАСТЕР В КАНДИДАТАХ (ЭТО ВАЖНО!)
#         # ═══════════════════════════════════════════════════════════
#         object_points = []

#         if len(object_candidates) >= 1:
#             object_candidates.sort(key=lambda x: x["index"])

#             clusters = []
#             current_cluster = [object_candidates[0]]

#             for i in range(1, len(object_candidates)):
#                 if object_candidates[i]["index"] - object_candidates[i-1]["index"] <= 3:
#                     current_cluster.append(object_candidates[i])
#                 else:
#                     clusters.append(current_cluster)
#                     current_cluster = [object_candidates[i]]

#             if current_cluster:
#                 clusters.append(current_cluster)

#             if clusters:
#                 best_cluster = max(clusters, key=len)
#                 object_points = [p["distance"] for p in best_cluster]
#                 logger.info(f"📦 Кластер объекта: {len(object_points)} точек")

#         # ═══════════════════════════════════════════════════════════
#         # 6. ОПРЕДЕЛЯЕМ СТАТУС
#         # ═══════════════════════════════════════════════════════════
#         points_count = len(object_points)

#         if points_count < 1:
#             is_empty = True
#             reason = "Нет точек объекта"
#             object_points = []
#         elif points_count <= self.EMPTY_POINTS_THRESHOLD:
#             is_empty = True
#             reason = f"Точек {points_count} <= {self.EMPTY_POINTS_THRESHOLD} (пусто)"
#         elif points_count >= self.FILLED_POINTS_THRESHOLD:
#             is_empty = False
#             reason = f"Точек {points_count} >= {self.FILLED_POINTS_THRESHOLD} (заполнено)"
#         else:
#             if points_count < 15:
#                 is_empty = True
#                 reason = f"Точек {points_count} в промежуточной зоне (скорее пусто)"
#             else:
#                 is_empty = False
#                 reason = f"Точек {points_count} в промежуточной зоне (скорее заполнено)"

#         # ═══════════════════════════════════════════════════════════
#         # 7. РАССЧИТЫВАЕМ ВЫСОТУ ОТ ПОЛА
#         # ═══════════════════════════════════════════════════════════
#         if object_points:
#             min_dist = min(object_points)
#             object_height = background_level - min_dist
#         else:
#             object_height = 0

#         logger.info(f"✅ Результат: {'ПУСТО' if is_empty else 'ЗАПОЛНЕН'} ({points_count} точек), высота={object_height}мм")

#         return {
#             "object_points": object_points,
#             "background_points": [p["distance"] for p in background_points],
#             "background_level": background_level,
#             "is_empty": is_empty,
#             "points_count": points_count,
#             "reason": reason,
#             "object_height_mm": object_height
#         }

#     def calculate_volume(self, distances_mm: List[int], floor_level_mm: int, box_profile, coal_density: float = 850, calibration_factor: float = 1.0) -> Dict[str, float]:
#         """
#         Рассчитывает объем и массу содержимого в коробке

#         Args:
#             distances_mm: массив расстояний до точек (мм)
#             floor_level_mm: уровень пола (мм)
#             box_profile: профиль коробки (с размерами)
#             coal_density: плотность угля (кг/м³), по умолчанию 850
#             calibration_factor: коэффициент калибровки (1.0 = без коррекции)

#         Returns:
#             {
#                 "volume_m3": float,        # Объем в куб.м
#                 "mass_tons": float,        # Масса в тоннах
#                 "height_mm": float,        # Средняя высота содержимого (мм)
#                 "fill_percent": float,     # % заполнения
#                 "cross_section_m2": float, # Площадь сечения
#                 "points_used": int,        # Количество точек использовано
#                 "raw_volume_m3": float,    # Объем без калибровки
#                 "calibration_factor": float # Примененный коэффициент
#             }
#         """
#         if not distances_mm or len(distances_mm) < 3:
#             return {
#                 "volume_m3": 0,
#                 "mass_tons": 0,
#                 "height_mm": 0,
#                 "fill_percent": 0,
#                 "cross_section_m2": 0,
#                 "points_used": 0,
#                 "raw_volume_m3": 0,
#                 "calibration_factor": calibration_factor
#             }

#         # Размеры коробки из профиля
#         box_width_m = box_profile.width_m
#         box_depth_m = box_profile.length_m
#         box_height_mm = box_profile.height_m * 1000

#         # ═══════════════════════════════════════════════════════════
#         # 1. РАССЧИТЫВАЕМ ВЫСОТУ СОДЕРЖИМОГО
#         # ═══════════════════════════════════════════════════════════
#         heights_mm = []
#         for d in distances_mm:
#             height = floor_level_mm - d
#             if height > 10:
#                 heights_mm.append(height)

#         if not heights_mm:
#             return {
#                 "volume_m3": 0,
#                 "mass_tons": 0,
#                 "height_mm": 0,
#                 "fill_percent": 0,
#                 "cross_section_m2": 0,
#                 "points_used": 0,
#                 "raw_volume_m3": 0,
#                 "calibration_factor": calibration_factor
#             }

#         # ═══════════════════════════════════════════════════════════
#         # 2. СРЕДНЯЯ ВЫСОТА (с удалением выбросов)
#         # ═══════════════════════════════════════════════════════════
#         sorted_heights = sorted(heights_mm)
#         trim_count = int(len(sorted_heights) * 0.1)
#         if trim_count > 0:
#             trimmed_heights = sorted_heights[trim_count:-trim_count]
#         else:
#             trimmed_heights = sorted_heights

#         avg_height_mm = sum(trimmed_heights) / len(trimmed_heights) if trimmed_heights else 0
#         avg_height_m = avg_height_mm / 1000

#         # ═══════════════════════════════════════════════════════════
#         # 3. ОБЪЕМ (RAW - без калибровки)
#         # ═══════════════════════════════════════════════════════════
#         cross_section_m2 = box_width_m * avg_height_m
#         raw_volume_m3 = cross_section_m2 * box_depth_m

#         # ═══════════════════════════════════════════════════════════
#         # 4. ПРИМЕНЯЕМ КАЛИБРОВКУ
#         # ═══════════════════════════════════════════════════════════
#         volume_m3 = raw_volume_m3 * calibration_factor

#         # ═══════════════════════════════════════════════════════════
#         # 5. ЗАПОЛНЕНИЕ
#         # ═══════════════════════════════════════════════════════════
#         fill_percent = (avg_height_mm / box_height_mm) * 100 if box_height_mm > 0 else 0
#         fill_percent = min(100, max(0, fill_percent))

#         # ═══════════════════════════════════════════════════════════
#         # 6. МАССА
#         # ═══════════════════════════════════════════════════════════
#         mass_tons = (volume_m3 * coal_density) / 1000

#         logger.info(f"📐 РАСЧЕТ ОБЪЕМА:")
#         logger.info(f"   Средняя высота: {avg_height_mm:.1f} мм ({avg_height_m:.3f} м)")
#         logger.info(f"   Ширина: {box_width_m:.2f} м, Глубина: {box_depth_m:.2f} м")
#         logger.info(f"   RAW объем: {raw_volume_m3:.4f} м³")
#         logger.info(f"   Объем: {volume_m3:.4f} м³, Масса: {mass_tons:.3f} т ({fill_percent:.1f}%)")

#         return {
#             "volume_m3": round(volume_m3, 4),
#             "mass_tons": round(mass_tons, 3),
#             "height_mm": round(avg_height_mm, 1),
#             "height_m": round(avg_height_m, 3),
#             "fill_percent": round(fill_percent, 1),
#             "cross_section_m2": round(cross_section_m2, 4),
#             "points_used": len(trimmed_heights),
#             "raw_volume_m3": round(raw_volume_m3, 4),
#             "calibration_factor": calibration_factor
#         }
    

#     def parse_scan_data(self, raw_data: str, filter_angle: bool = True, separate_object: bool = True, mode: str = "auto") -> Dict[str, Any]:
#         """
#         Парсинг данных лидара с АНАЛИЗОМ УГЛОВ (как на фронтенде) + ObjectDetector
#         """
#         try:
#             if not raw_data:
#                 return {"error": "Нет данных", "valid": False}

#             #  ИСПОЛЬЗУЕМ parse_raw_data() ДЛЯ ПАРСИНГА!
#             raw_distances = self.parse_raw_data(raw_data)

#             result = {
#                 "valid": True,
#                 "timestamp": time.time(),
#                 "distances_mm_raw": raw_distances,
#                 "distances_mm": [],
#                 "distances_m": [],
#                 "points_count": 0,
#                 "is_filtered": False,
#                 "object_detected": False,
#                 "floor_level_mm": self.FLOOR_LEVEL,
#                 "is_empty": True,
#                 "empty_confidence": 0,
#                 "empty_reason": "",
#                 "object_type": "unknown",
#                 "object_height_mm": 0,
#                 "spread_mm": 0,
#                 "box_info": {}
#             }

#             result["scan_geometry"] = self.get_scan_geometry(raw_data)

#             logger.info(f" Сырых точек: {len(raw_distances)}")

#             # ═══════════════════════════════════════════════════════════
#             # 2. ФИЛЬТРАЦИЯ УГЛА (70°)
#             # ═══════════════════════════════════════════════════════════
#             if filter_angle and raw_distances:
#                 filtered_angle = self.filter_angle(raw_distances, 70)
#                 logger.info(f" После фильтрации угла: {len(filtered_angle)} точек")
#                 current_points = filtered_angle
#             else:
#                 current_points = raw_distances

#             # ═══════════════════════════════════════════════════════════
#             # 3. ФИЛЬТРАЦИЯ ШУМА
#             # ═══════════════════════════════════════════════════════════
#             if current_points:
#                 valid_points = [d for d in current_points
#                                 if self.MIN_VALID_DISTANCE <= d <= 3000]

#                 logger.info(f"🔍 После фильтрации шума: {len(valid_points)} точек")
#                 current_points = valid_points

#             # ═══════════════════════════════════════════════════════════
#             # 4.  АНАЛИЗ С УЧЕТОМ УГЛОВ
#             # ═══════════════════════════════════════════════════════════
#             if current_points and separate_object:
#                 analysis = self.analyze_scan_with_angles(current_points)

#                 object_points = analysis.get("object_points", [])
#                 background_level = analysis.get("background_level", self.FLOOR_LEVEL)
#                 is_empty = analysis.get("is_empty", True)
#                 reason = analysis.get("reason", "")

#                 logger.info(f"📊 Анализ с углами завершен:")
#                 logger.info(f"   Объект: {len(object_points)} точек")
#                 logger.info(f"   Фон: {background_level} мм")
#                 logger.info(f"   Статус: {'ПУСТО' if is_empty else 'ЗАПОЛНЕН'}")

#                 if object_points and len(object_points) >= 1:
#                     min_dist = min(object_points)
#                     max_dist = max(object_points)
#                     object_height = background_level - min_dist
#                     spread = max_dist - min_dist

#                     result["object_detected"] = True
#                     result["distances_mm"] = object_points
#                     result["points_count"] = len(object_points)
#                     result["floor_level_mm"] = self.FLOOR_LEVEL
#                     result["is_empty"] = is_empty
#                     result["empty_reason"] = reason
#                     result["object_height_mm"] = object_height
#                     result["spread_mm"] = spread

#                     if is_empty:
#                         result["empty_confidence"] = 90
#                     else:
#                         result["empty_confidence"] = 85

#                     if mode == "auto":
#                         if len(object_points) < 50:
#                             detection_mode = "test_box"
#                             logger.info("Автоопределение: режим TEST_BOX")
#                         else:
#                             detection_mode = "truck"
#                             logger.info("Автоопределение: режим TRUCK")
#                     else:
#                         detection_mode = mode

#                     detection_result = ObjectDetector.process_scan(
#                         object_points,
#                         {"mode": detection_mode, "floor_level": self.FLOOR_LEVEL}
#                     )

#                     result["object_type"] = detection_result.get("object_type", "box")

#                     box_info = detection_result.get("box_info", {})
#                     if box_info.get("detected"):
#                         result["box_info"] = box_info
#                         logger.info(f"📦 Определен тип коробки: {box_info.get('box_label', '?')}")

#                     profile = detection_result.get("profile")
#                     if profile:
#                         result["profile"] = profile
#                         result["profile_confidence"] = detection_result.get("profile_confidence", 0)

#                     logger.info(f"✅ ObjectDetector: {result['object_type']}, пусто={result['is_empty']}, точек={result['points_count']}")

#                 else:
#                     result["object_detected"] = False
#                     result["distances_mm"] = []
#                     result["points_count"] = 0
#                     result["is_empty"] = True
#                     result["empty_confidence"] = 95
#                     result["empty_reason"] = "Объект не обнаружен"
#                     result["object_type"] = "none"
#                     result["object_height_mm"] = 0
#                     result["spread_mm"] = 0
#                     result["floor_level_mm"] = self.FLOOR_LEVEL
#                     result["box_info"] = {}

#                     logger.info(f"📭 Объект не обнаружен")
#             else:
#                 result["distances_mm"] = current_points or []
#                 result["points_count"] = len(result["distances_mm"])
#                 if result["points_count"] == 0:
#                     result["is_empty"] = True
#                     result["empty_reason"] = "Нет данных"

#             # ═══════════════════════════════════════════════════════════
#             # 8. СТАТИСТИКА
#             # ═══════════════════════════════════════════════════════════
#             if result["distances_mm"]:
#                 result["distances_m"] = [round(d/1000, 2) for d in result["distances_mm"]]

#                 valid_dist = [d for d in result["distances_mm"] if 0 < d < 50000]
#                 if valid_dist:
#                     result["min_distance_mm"] = min(valid_dist)
#                     result["max_distance_mm"] = max(valid_dist)
#                     result["avg_distance_mm"] = sum(valid_dist) // len(valid_dist)
#                     result["min_distance_m"] = round(min(valid_dist)/1000, 2)
#                     result["max_distance_m"] = round(max(valid_dist)/1000, 2)
#                     result["avg_distance_m"] = round(sum(valid_dist)/len(valid_dist)/1000, 2)

#             logger.info(f"📊 Итог: точек={result['points_count']}, пусто={result['is_empty']}, тип={result['object_type']}")
#             return result

#         except Exception as e:
#             logger.error(f"Ошибка парсинга: {e}", exc_info=True)
#             return {"error": str(e), "valid": False}

     
        
        

#     def disconnect(self):
#         if self.sock:
#             try:
#                 self.sock.close()
#             except:
#                 pass
#             self.is_connected = False
#             logger.info("🔌 Отключен")

#     def check_if_empty(self, scan_data: Dict) -> Dict:
#         return ObjectDetector.process_scan(scan_data.get("distances_mm", []))


# # Глобальный экземпляр
# lidar_client = LidarClient()