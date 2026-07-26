

# backend/services/object_detector.py
"""
Детектор объектов - использует vehicle_profiles для определения типа и статуса
"""
import logging
import numpy as np
import math
from typing import Dict, List, Any, Optional, Tuple
from collections import Counter, deque
from services.vehicle_profiles import vehicle_profiles

logger = logging.getLogger(__name__)


class ObjectDetector:
    """
    Обнаружение и анализ объектов на сцене
    Использует базу профилей для идентификации
    """

    # ═══════════════════════════════════════════════════════════
    # КОНСТАНТЫ ФИЛЬТРАЦИИ
    # ═══════════════════════════════════════════════════════════
    MIN_VALID_DISTANCE = 100      # мм
    MAX_VALID_DISTANCE = 3000     # мм
    FLOOR_THRESHOLD = 150         # мм - отсечение пола
    MIN_POINTS_FOR_OBJECT = 5     # Минимум точек для объекта

    # ПОРОГИ ОПРЕДЕЛЕНИЯ ПУСТОТЫ
    EMPTY_POINTS_THRESHOLD = 10   # Если <= 10 точек - пусто
    FILLED_POINTS_THRESHOLD = 17  # Если >= 17 точек - заполнено

    # ═══════════════════════════════════════════════════════════
    # ⭐ БУФЕРЫ ДЛЯ СТАБИЛИЗАЦИИ
    # ═══════════════════════════════════════════════════════════
    _width_history = deque(maxlen=5)
    _box_type_history = deque(maxlen=5)
    _height_history = deque(maxlen=5)

    @classmethod
    def _stabilize_width(cls, width_mm: float) -> Tuple[float, bool]:
        """
        Стабилизирует измерение ширины через медианный фильтр.

        Returns:
            (стабилизированная_ширина, была_ли_коррекция)
        """
        # Добавляем текущее измерение
        cls._width_history.append(width_mm)

        # Если истории мало - возвращаем текущее значение
        if len(cls._width_history) < 3:
            return width_mm, False

        # Медианная фильтрация
        sorted_history = sorted(cls._width_history)
        median = sorted_history[len(sorted_history) // 2]

        # Если текущее измерение сильно отличается от медианы (> 30 мм)
        if abs(width_mm - median) > 30:
            logger.info(f"📊 Стабилизация ширины: {width_mm:.1f} → {median:.1f} мм")
            return median, True

        return width_mm, False

    @classmethod
    def _stabilize_height(cls, height_mm: float) -> Tuple[float, bool]:
        """
        Стабилизирует измерение высоты через медианный фильтр.
        """
        cls._height_history.append(height_mm)

        if len(cls._height_history) < 3:
            return height_mm, False

        sorted_history = sorted(cls._height_history)
        median = sorted_history[len(sorted_history) // 2]

        if abs(height_mm - median) > 20:
            logger.info(f"📊 Стабилизация высоты: {height_mm:.1f} → {median:.1f} мм")
            return median, True

        return height_mm, False

    @classmethod
    def _stabilize_box_type(cls, box_type: str, confidence: float) -> Tuple[str, float]:
        """
        Стабилизирует определение типа коробки.
        """
        cls._box_type_history.append({
            "type": box_type,
            "confidence": confidence
        })

        if len(cls._box_type_history) < 3:
            return box_type, confidence

        # Считаем частоту каждого типа
        type_counts = {}
        for item in cls._box_type_history:
            type_counts[item["type"]] = type_counts.get(item["type"], 0) + 1

        # Выбираем наиболее частый тип
        most_common = max(type_counts.items(), key=lambda x: x[1])

        # Если самый частый тип встречается > 50% времени
        if most_common[1] / len(cls._box_type_history) > 0.5:
            avg_confidence = sum(item["confidence"] for item in cls._box_type_history
                                if item["type"] == most_common[0]) / most_common[1]
            return most_common[0], min(95, avg_confidence + 10)

        return box_type, confidence

    @classmethod
    def process_scan(cls, distances_mm: List[int], params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Основной метод обработки скана

        Args:
            distances_mm: массив расстояний в мм
            params: параметры обработки
                - mode: "box" | "truck" | "auto" (по умолчанию "auto")
                - floor_level: уровень пола (если известен)
        """
        if not distances_mm:
            return cls._empty_result("Нет данных", "no_data")

        params = params or {}

        # ═══════════════════════════════════════════════════════════
        # ШАГ 1: БАЗОВАЯ ФИЛЬТРАЦИЯ
        # ═══════════════════════════════════════════════════════════
        filtered = cls._filter_noise(distances_mm)
        valid_points = cls._filter_valid_distances(filtered)

        if len(valid_points) < cls.MIN_POINTS_FOR_OBJECT:
            return cls._empty_result("Мало валидных точек", "no_object")

        # ═══════════════════════════════════════════════════════════
        # ШАГ 2: ОПРЕДЕЛЕНИЕ УРОВНЯ ПОЛА
        # ═══════════════════════════════════════════════════════════
        floor_level = params.get("floor_level", cls._find_floor_level(valid_points))

        # ═══════════════════════════════════════════════════════════
        # ШАГ 3: ОТСЕЧЕНИЕ ПОЛА - НАХОДИМ ТОЧКИ ОБЪЕКТА
        # ═══════════════════════════════════════════════════════════
        object_points = cls._extract_object_points(valid_points, floor_level)

        if not object_points or len(object_points) < cls.MIN_POINTS_FOR_OBJECT:
            return cls._empty_result("Объект не обнаружен", "no_object", floor_level=floor_level)

        # ═══════════════════════════════════════════════════════════
        # ШАГ 4: РАСЧЕТ ХАРАКТЕРИСТИК ОБЪЕКТА
        # ═══════════════════════════════════════════════════════════
        points_count = len(object_points)
        min_dist = min(object_points)
        max_dist = max(object_points)
        object_height = floor_level - min_dist
        spread = max_dist - min_dist
        avg_dist = sum(object_points) / len(object_points)

        #  СТАБИЛИЗАЦИЯ ВЫСОТЫ
        stabilized_height, height_corrected = cls._stabilize_height(object_height)
        if height_corrected:
            object_height = stabilized_height

        logger.info(f"📊 Объект: {points_count} точек, высота={object_height:.1f}мм, разброс={spread:.1f}мм")

        # ═══════════════════════════════════════════════════════════════
        #  НОВЫЙ ШАГ: ФИЛЬТРАЦИЯ ОБЪЕКТА (ДО ОПРЕДЕЛЕНИЯ РЕЖИМА!)
        # ═══════════════════════════════════════════════════════════════
        if points_count > 10:
            # Отбрасываем точки дальше 300 мм от минимума (пол и шум)
            threshold = min_dist + 300
            filtered_object_points = [d for d in object_points if d <= threshold]

            if len(filtered_object_points) >= cls.MIN_POINTS_FOR_OBJECT:
                logger.info(f"📦 Фильтрация объекта: {len(filtered_object_points)} точек из {points_count}")
                logger.info(f"   Минимальное расстояние: {min_dist} мм, порог: {threshold} мм")

                object_points = filtered_object_points
                points_count = len(object_points)
                min_dist = min(object_points)
                max_dist = max(object_points)
                object_height = floor_level - min_dist
                spread = max_dist - min_dist
                avg_dist = sum(object_points) / len(object_points)

                logger.info(f"   После фильтрации: {points_count} точек, высота={object_height:.1f}мм")

        # ═══════════════════════════════════════════════════════════
        # ⭐ ШАГ 4.5: ОПРЕДЕЛЕНИЕ РЕЖИМА РАБОТЫ
        # ═══════════════════════════════════════════════════════════
        mode = params.get("mode", "auto")

        if mode == "box":
            logger.info("🟢 Режим: КОРОБКА (принудительный)")
            return cls._process_box_mode(object_points, floor_level, valid_points)
        elif mode == "truck":
            logger.info("🔵 Режим: ГРУЗОВИК (принудительный)")
            return cls._process_truck_mode(object_points, floor_level, valid_points)
        else:
            # Автоопределение
            if points_count < 50:
                logger.info("🟢 Автоопределение: режим КОРОБОК (мало точек)")
                return cls._process_box_mode(object_points, floor_level, valid_points)
            else:
                logger.info("🔵 Автоопределение: режим ГРУЗОВИК (много точек)")
                return cls._process_truck_mode(object_points, floor_level, valid_points)

    # ═══════════════════════════════════════════════════════════
    # ⭐ РЕЖИМ КОРОБОК - ФИКСИРОВАННАЯ ШИРИНА
    # ═══════════════════════════════════════════════════════════

    @classmethod
    def _process_box_mode(cls, object_points: List[int], floor_level: int, all_points: List[int] = None) -> Dict[str, Any]:
        """
        Обработка скана для КОРОБОК.
        Используем ФИКСИРОВАННУЮ ширину из профиля.
        Отбрасываем точки вне коробки (пол, стены).
        """
        # ═══════════════════════════════════════════════════════════
        # ⭐ 1. ОТБРАСЫВАЕМ ТОЧКИ ВНЕ КОРОБКИ (ТОЛЬКО ОБЪЕКТ!)
        # ═══════════════════════════════════════════════════════════

        # Находим минимальное расстояние (самая близкая точка к лидару)
        min_dist = min(object_points)

        # Объект - это точки в пределах 300 мм от минимального расстояния
        # (это захватывает всю коробку/кирпич, но не пол)
        threshold = min_dist + 300
        filtered_points = [d for d in object_points if d <= threshold]

        logger.info(f"📦 Отфильтровано точек: {len(filtered_points)} из {len(object_points)}")
        logger.info(f"   Минимальное расстояние: {min_dist} мм")
        logger.info(f"   Порог отсечения: {threshold} мм")

        if len(filtered_points) < cls.MIN_POINTS_FOR_OBJECT:
            logger.warning(f"⚠️ После фильтрации осталось {len(filtered_points)} точек (меньше минимума)")
            return cls._empty_result("Мало точек объекта после фильтрации", "no_object", floor_level=floor_level)

        # Используем отфильтрованные точки
        object_points = filtered_points
        points_count = len(object_points)
        min_dist = min(object_points)
        max_dist = max(object_points)
        object_height = floor_level - min_dist
        spread = max_dist - min_dist
        avg_dist = sum(object_points) / len(object_points)

        # ═══════════════════════════════════════════════════════════
        # 2. ОПРЕДЕЛЯЕМ ТИП КОРОБКИ ПО ВЫСОТЕ
        # ═══════════════════════════════════════════════════════════
        box_type, confidence, width_mm = cls._determine_box_type_by_height(object_height, points_count)

        # ═══════════════════════════════════════════════════════════
        # 3. СТАБИЛИЗАЦИЯ ТИПА
        # ═══════════════════════════════════════════════════════════
        stable_type, stable_confidence = cls._stabilize_box_type(box_type, confidence)
        if stable_type != box_type:
            logger.info(f"📊 Стабилизация типа: {box_type} → {stable_type}")
            box_type = stable_type
            confidence = stable_confidence
            if box_type == "medium":
                width_mm = 350
            else:
                width_mm = 400

        # ═══════════════════════════════════════════════════════════
        # 4. НАХОДИМ ПРОФИЛЬ
        # ═══════════════════════════════════════════════════════════
        profile = None
        for name, p in vehicle_profiles.profiles.items():
            if p.vehicle_type == "box" and p.box_type == box_type:
                profile = p
                logger.info(f"🔍 Найден профиль: {name} (уверенность: {confidence}%)")
                break

        # Fallback - если профиль не найден, используем M
        if not profile:
            profile = vehicle_profiles.get_profile("Коробка M (35x65x37)")
            width_mm = 350
            confidence = 50
            logger.warning(f"⚠️ Профиль не найден, используем M по умолчанию")

        # ═══════════════════════════════════════════════════════════
        # 5. ОПРЕДЕЛЕНИЕ СТАТУСА
        # ═══════════════════════════════════════════════════════════
        status_result = cls._determine_status(points_count, object_height, profile, spread)

        # ═══════════════════════════════════════════════════════════
        # 6. ИНФОРМАЦИЯ О КОРОБКЕ
        # ═══════════════════════════════════════════════════════════
        box_info = vehicle_profiles.get_box_info_from_profile(profile)
        box_info["profile_confidence"] = confidence

        if profile and profile.vehicle_type == "box" and box_info.get("detected"):
            size_str = f"{box_info['size_cm']['width']}×{box_info['size_cm']['depth']}×{box_info['size_cm']['height']}"
            if status_result["is_empty"]:
                status_text = f"📦 Коробка {box_info['box_label']} ({size_str}см) ПУСТАЯ"
            else:
                status_text = f"📦 Коробка {box_info['box_label']} ({size_str}см) ЗАПОЛНЕНА"
        else:
            if status_result["is_empty"]:
                status_text = "📭 Объект ПУСТОЙ"
            else:
                status_text = "📦 Объект ЗАПОЛНЕН"

        logger.info(f"📦 РЕЖИМ КОРОБОК: {box_type} (ширина: {width_mm}мм, уверенность: {confidence}%)")
        logger.info(f"   Точек после фильтрации: {points_count}")

        return {
            "mode": "box",
            "object_detected": True,
            "is_empty": status_result["is_empty"],
            "confidence": status_result["confidence"],
            "object_status": status_result["status"],
            "status_text": status_text,
            "object_type": "box",
            "profile": profile,
            "profile_confidence": confidence,
            "box_info": box_info,
            "points_count": points_count,
            "object_height_mm": object_height,
            "floor_level_mm": floor_level,
            "spread_mm": spread,
            "width_mm": width_mm,  # ← ФИКСИРОВАННАЯ
            "avg_distance_mm": avg_dist,
            "reason": status_result["reason"],
            "points": object_points,
            "all_points": all_points or object_points,
            "box_type_detected": box_type,
            "box_confidence": confidence,
            "height_stabilized": False,
            "width_stabilized": False,
            "points_filtered": len(filtered_points)  # ← ДОБАВЛЯЕМ
        }

    # ═══════════════════════════════════════════════════════════
    # ⭐ РЕЖИМ ГРУЗОВИКОВ - ИЗМЕРЯЕМ РЕАЛЬНЫЕ РАЗМЕРЫ
    # ═══════════════════════════════════════════════════════════

    @classmethod
    def _process_truck_mode(cls, object_points: List[int], floor_level: int, all_points: List[int] = None) -> Dict[str, Any]:
        """
        Обработка скана для ГРУЗОВИКОВ.

        Особенности:
        - Кузова имеют РАЗНЫЕ размеры
        - Измеряем РЕАЛЬНУЮ ширину и длину
        - Используем АЛГОРИТМ ПО КРАЯМ
        - Разница 500-1000 мм - легко определяется
        """
        points_count = len(object_points)
        min_dist = min(object_points)
        max_dist = max(object_points)
        object_height = floor_level - min_dist
        spread = max_dist - min_dist
        avg_dist = sum(object_points) / len(object_points)

        # ═══════════════════════════════════════════════════════════
        # ⭐ ИЗМЕРЯЕМ РЕАЛЬНУЮ ШИРИНУ (по краям)
        # ═══════════════════════════════════════════════════════════
        width_info = cls._measure_truck_width(object_points, floor_level)
        width_mm = width_info.get("width_mm", 0)

        logger.info(f"🚛 Измеренная ширина грузовика: {width_mm:.1f}мм")

        # ═══════════════════════════════════════════════════════════
        # ⭐ ИЩЕМ ПРОФИЛЬ ГРУЗОВИКА ПО РАЗМЕРАМ
        # ═══════════════════════════════════════════════════════════
        profile, confidence = cls._find_truck_profile_by_size(width_mm, object_height)

        if not profile:
            # Используем стандартный профиль
            profile = vehicle_profiles.get_profile("КАМАЗ 65115")
            confidence = 40
            logger.warning(f"⚠️ Профиль не найден, используем КАМАЗ 65115 по умолчанию")

        # ═══════════════════════════════════════════════════════════
        # ФИЛЬТРАЦИЯ ТОЧЕК ПО ПРОФИЛЮ
        # ═══════════════════════════════════════════════════════════
        if profile and confidence > 30:
            filtered_points = cls._filter_points_by_profile(object_points, profile, floor_level)
            if filtered_points:
                object_points = filtered_points
                points_count = len(object_points)
                min_dist = min(object_points)
                max_dist = max(object_points)
                object_height = floor_level - min_dist
                spread = max_dist - min_dist
                avg_dist = sum(object_points) / len(object_points)
                logger.info(f"📦 После фильтрации: {points_count} точек")

        # ═══════════════════════════════════════════════════════════
        # ОПРЕДЕЛЕНИЕ СТАТУСА
        # ═══════════════════════════════════════════════════════════
        status_result = cls._determine_status(points_count, object_height, profile, spread)

        # ═══════════════════════════════════════════════════════════
        # ФОРМИРОВАНИЕ СТАТУСА
        # ═══════════════════════════════════════════════════════════
        if status_result["is_empty"]:
            status_text = f"🚛 {profile.name if profile else 'Грузовик'} - ПУСТОЙ"
        else:
            status_text = f"🚛 {profile.name if profile else 'Грузовик'} - ЗАПОЛНЕН"

        # Информация о коробке (для совместимости)
        box_info = {
            "box_type": "truck",
            "box_label": "🚛",
            "box_name": profile.name if profile else "Грузовик",
            "size_mm": {
                "width": int(width_mm),
                "depth": int(profile.length_m * 1000) if profile else 0,
                "height": int(object_height)
            },
            "size_cm": {
                "width": round(width_mm / 10, 1),
                "depth": round(profile.length_m * 100, 1) if profile else 0,
                "height": round(object_height / 10, 1)
            },
            "detected": True,
            "confidence": confidence,
            "profile_name": profile.name if profile else None,
            "vehicle_type": "truck"
        }

        logger.info(f"🚛 РЕЖИМ ГРУЗОВИК: ширина={width_mm:.1f}мм, высота={object_height:.1f}мм")

        return {
            "mode": "truck",
            "object_detected": True,
            "is_empty": status_result["is_empty"],
            "confidence": status_result["confidence"],
            "object_status": status_result["status"],
            "status_text": status_text,
            "object_type": "truck",
            "profile": profile,
            "profile_confidence": confidence,
            "box_info": box_info,
            "points_count": points_count,
            "object_height_mm": object_height,
            "floor_level_mm": floor_level,
            "spread_mm": spread,
            "width_mm": width_mm,  # ← ИЗМЕРЕННАЯ
            "avg_distance_mm": avg_dist,
            "reason": status_result["reason"],
            "points": object_points,
            "all_points": all_points or object_points,
            "width_info": width_info,
            "height_stabilized": False,  # Уже применено в process_scan
            "width_stabilized": width_info.get("was_corrected", False)
        }

    # ═══════════════════════════════════════════════════════════
    # ⭐ ИЗМЕРЕНИЕ ШИРИНЫ ГРУЗОВИКА (ПО КРАЯМ)
    # ═══════════════════════════════════════════════════════════

    @classmethod
    def _measure_truck_width(cls, distances_mm: List[int], floor_level: int) -> Dict[str, float]:
        """
        Измеряет ширину грузовика по КРАЯМ.

        Для грузовиков это работает хорошо, потому что:
        1. Разница между кузовами 500-1000 мм
        2. Края четкие (борта кузова)
        3. Точности лидара достаточно
        """
        if not distances_mm or len(distances_mm) < 10:
            return {
                "width_mm": 0,
                "method": "no_data",
                "was_corrected": False
            }

        # ═══════════════════════════════════════════════════════════
        # 1. Находим точки объекта (не пол)
        # ═══════════════════════════════════════════════════════════
        object_points = [d for d in distances_mm if d < floor_level - 50]

        if len(object_points) < 5:
            return {
                "width_mm": 0,
                "method": "no_object",
                "was_corrected": False
            }

        # ═══════════════════════════════════════════════════════════
        # 2. Находим КРАЯ по ПЕРЕПАДАМ (градиентам)
        # ═══════════════════════════════════════════════════════════

        # Вычисляем градиенты (перепады между соседними точками)
        gradients = []
        for i in range(2, len(distances_mm) - 2):
            grad = abs(distances_mm[i+2] - distances_mm[i-2]) / 4
            if grad > 20:  # Минимальный порог для грузовиков (выше, чем для коробок)
                gradients.append((i, grad))

        if len(gradients) < 2:
            # Не нашли два явных края - используем весь диапазон
            left_idx = 0
            right_idx = len(distances_mm) - 1
            logger.warning(f"⚠️ Края грузовика не найдены, используем весь диапазон")
        else:
            sorted_grads = sorted(gradients, key=lambda x: x[1], reverse=True)
            left_idx = min(sorted_grads[0][0], sorted_grads[1][0])
            right_idx = max(sorted_grads[0][0], sorted_grads[1][0])

            # Проверяем, что перепады достаточно большие (для грузовиков)
            if sorted_grads[0][1] < 50 or sorted_grads[1][1] < 50:
                logger.warning(f"⚠️ Перепады грузовика слишком маленькие: {sorted_grads[0][1]:.1f}, {sorted_grads[1][1]:.1f}")
                left_idx = 0
                right_idx = len(distances_mm) - 1

        # ═══════════════════════════════════════════════════════════
        # 3. Переводим индексы в физическую ширину
        # ═══════════════════════════════════════════════════════════

        total_points = len(distances_mm)
        total_angle_deg = 70  # -35° до +35°

        idx_spread = right_idx - left_idx
        angle_deg = (idx_spread / total_points) * total_angle_deg if total_points > 0 else 0

        # Среднее расстояние до объекта
        avg_dist = sum(object_points) / len(object_points) if object_points else 2600

        # Ширина = 2 * расстояние * tan(угол/2)
        angle_rad = math.radians(angle_deg / 2)
        width_mm = 2 * avg_dist * math.tan(angle_rad) if angle_deg > 0 else 0

        # ═══════════════════════════════════════════════════════════
        # 4. ⭐ ПРИМЕНЯЕМ СТАБИЛИЗАЦИЮ
        # ═══════════════════════════════════════════════════════════
        stabilized_width, was_corrected = cls._stabilize_width(width_mm)

        # ═══════════════════════════════════════════════════════════
        # 5. ДИАГНОСТИКА
        # ═══════════════════════════════════════════════════════════
        logger.info(f"🚛 ИЗМЕРЕНИЕ ШИРИНЫ ГРУЗОВИКА:")
        logger.info(f"   Индексы: {left_idx} → {right_idx} (разброс: {idx_spread})")
        logger.info(f"   Угол: {angle_deg:.1f}°")
        logger.info(f"   Среднее расстояние: {avg_dist:.0f} мм")
        logger.info(f"   Ширина: {width_mm:.1f} → стабилизировано: {stabilized_width:.1f} мм")

        return {
            "width_mm": round(stabilized_width, 1),
            "left_edge": left_idx,
            "right_edge": right_idx,
            "idx_spread": idx_spread,
            "angle_deg": round(angle_deg, 1),
            "avg_distance": round(avg_dist, 1),
            "raw_width": round(width_mm, 1),
            "was_corrected": was_corrected,
            "method": "edges",
            "gradients_found": len(gradients)
        }

    # ═══════════════════════════════════════════════════════════
    # ⭐ ПОИСК ПРОФИЛЯ ГРУЗОВИКА ПО РАЗМЕРАМ
    # ═══════════════════════════════════════════════════════════

    @classmethod
    def _find_truck_profile_by_size(cls, width_mm: float, height_mm: float) -> Tuple[Optional[Any], float]:
        """
        Находит профиль грузовика по размерам
        """
        best_profile = None
        best_score = 0

        for name, profile in vehicle_profiles.profiles.items():
            if profile.vehicle_type not in ["truck", "trailer", "wagon"]:
                continue

            expected_width = profile.width_m * 1000
            expected_height = profile.height_m * 1000

            # Оценка по ширине (вес 0.7)
            if expected_width > 0:
                width_diff = abs(width_mm - expected_width) / expected_width
                width_score = max(0, 100 - width_diff * 100)
            else:
                width_score = 0

            # Оценка по высоте (вес 0.3)
            if expected_height > 0:
                height_diff = abs(height_mm - expected_height) / expected_height
                height_score = max(0, 100 - height_diff * 100)
            else:
                height_score = 0

            # Итоговый скор
            score = width_score * 0.7 + height_score * 0.3

            if score > best_score:
                best_score = score
                best_profile = profile

        logger.info(f"🚛 Поиск профиля грузовика: ширина={width_mm:.1f}мм, высота={height_mm:.1f}мм")
        if best_profile:
            logger.info(f"   Найден: {best_profile.name} (score: {best_score:.1f}%)")
        else:
            logger.info(f"   Профиль не найден")

        return best_profile, best_score if best_score > 40 else 0

    # ═══════════════════════════════════════════════════════════
    # ⭐ ОПРЕДЕЛЕНИЕ ТИПА КОРОБКИ ПО ВЫСОТЕ
    # ═══════════════════════════════════════════════════════════

    @classmethod
    def _determine_box_type_by_height(cls, height_mm: float, points_count: int) -> Tuple[str, float, int]:
        """
        Определяет тип коробки по высоте и количеству точек.

        Для коробок M и L:
        - M: 370 мм высота, 350 мм ширина
        - L: 600 мм высота, 400 мм ширина

        Но! Коробка может быть не полностью заполнена,
        поэтому используем эвристики.
        """
        # Если высота очень маленькая - коробка почти пустая
        # Используем M по умолчанию
        if height_mm < 100:
            return "medium", 50, 350

        # ═══════════════════════════════════════════════════════════
        # ПРАВИЛА ОПРЕДЕЛЕНИЯ
        # ═══════════════════════════════════════════════════════════

        if height_mm < 200:
            # Низкая высота - скорее M (или почти пустая L)
            box_type = "medium"
            confidence = 60
            width_mm = 350
            reason = "низкая высота (< 200мм) → M"

        elif height_mm < 350:
            # Средняя высота
            if points_count > 20:
                # Много точек - скорее L (больше площадь)
                box_type = "large"
                confidence = 55
                width_mm = 400
                reason = "средняя высота + много точек → L"
            else:
                box_type = "medium"
                confidence = 65
                width_mm = 350
                reason = "средняя высота + мало точек → M"

        elif height_mm < 500:
            # Выше среднего
            if points_count > 18:
                box_type = "large"
                confidence = 70
                width_mm = 400
                reason = "выше среднего + много точек → L"
            else:
                box_type = "large"
                confidence = 60
                width_mm = 400
                reason = "выше среднего → L"

        else:
            # Высокая коробка
            box_type = "large"
            confidence = 80
            width_mm = 400
            reason = "высокая → L"

        logger.info(f"📏 Определение типа по высоте:")
        logger.info(f"   Высота: {height_mm:.1f} мм")
        logger.info(f"   Точек: {points_count}")
        logger.info(f"   Тип: {box_type} (ширина: {width_mm} мм, уверенность: {confidence}%)")
        logger.info(f"   Причина: {reason}")

        return box_type, confidence, width_mm

    # ═══════════════════════════════════════════════════════════
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ═══════════════════════════════════════════════════════════

    @classmethod
    def _empty_result(cls, reason: str, status: str, floor_level: int = 0) -> Dict[str, Any]:
        return {
            "object_detected": False,
            "is_empty": True,
            "confidence": 100 if status == "no_data" else 95,
            "object_status": status,
            "status_text": "📭 Объект отсутствует" if status == "no_object" else "❌ Нет данных",
            "object_type": "none",
            "profile": None,
            "profile_confidence": 0,
            "box_info": {
                "box_type": "unknown",
                "box_label": "?",
                "box_name": "Неизвестная",
                "size_mm": {"width": 0, "depth": 0, "height": 0},
                "size_cm": {"width": 0, "depth": 0, "height": 0},
                "detected": False,
                "confidence": 0,
                "profile_name": None
            },
            "points_count": 0,
            "object_height_mm": 0,
            "floor_level_mm": floor_level,
            "spread_mm": 0,
            "width_mm": 0,
            "avg_distance_mm": 0,
            "reason": reason,
            "points": []
        }

    @classmethod
    def _filter_noise(cls, distances_mm: List[int]) -> List[int]:
        if len(distances_mm) < 3:
            return distances_mm

        filtered = []
        window_size = 3

        for i in range(len(distances_mm)):
            start = max(0, i - window_size // 2)
            end = min(len(distances_mm), i + window_size // 2 + 1)
            window = distances_mm[start:end]
            filtered.append(int(np.median(window)))

        return filtered

    @classmethod
    def _filter_valid_distances(cls, distances_mm: List[int]) -> List[int]:
        return [d for d in distances_mm if cls.MIN_VALID_DISTANCE <= d <= cls.MAX_VALID_DISTANCE]

    @classmethod
    def _find_floor_level(cls, distances_mm: List[int]) -> int:
        """
        Находит уровень пола.
        distances_mm уже содержат РЕАЛЬНЫЕ расстояния (со смещением +1000).
        """
        if not distances_mm:
            return 2792  # Фиксированный пол

        # ⭐ Ищем пол в диапазоне 2500-3000 мм (с учетом смещения)
        floor_candidates = [d for d in distances_mm if 2500 <= d <= 3000]

        if floor_candidates:
            counter = Counter(floor_candidates)
            floor_level = counter.most_common(1)[0][0]
            logger.info(f"🏗️ Уровень пола (из диапазона 2500-3000): {floor_level} мм")
            return floor_level

        # Fallback - фиксированный пол
        logger.info(f"🏗️ Уровень пола (fallback): 2792 мм")
        return 2792

    @classmethod
    def _extract_object_points(cls, distances_mm: List[int], floor_level: int) -> List[int]:
        """Извлекает точки объекта, отсекая пол"""
        if not distances_mm:
            return []

        floor_threshold = 80  # мм - чуть больше, чтобы отсечь шум

        object_points = [d for d in distances_mm
                        if d < floor_level - floor_threshold]

        # ✅ НЕ ВОЗВРАЩАЕМ ВСЕ ТОЧКИ!
        # Если мало точек - возвращаем пустой список
        if len(object_points) < cls.MIN_POINTS_FOR_OBJECT:
            logger.warning(f"⚠️ Мало точек объекта: {len(object_points)} из {len(distances_mm)}")
            return []  # ← ПУСТОЙ СПИСОК!

        return object_points

    # ═══════════════════════════════════════════════════════════
    # МЕТОДЫ ФИЛЬТРАЦИИ ПО ГРАНИЦАМ ОБЪЕКТА
    # ═══════════════════════════════════════════════════════════

    @classmethod
    def _filter_points_by_profile(cls, distances_mm: List[int], profile, floor_level: int) -> List[int]:
        if not profile or not distances_mm:
            return distances_mm

        try:
            filtered = profile.filter_points_inside(distances_mm, floor_level)
        except AttributeError:
            filtered = cls._filter_points_by_profile_fallback(distances_mm, profile, floor_level)

        logger.info(f"📦 Фильтрация по профилю {profile.name}:")
        logger.info(f"  Было: {len(distances_mm)} точек")
        logger.info(f"  Стало: {len(filtered)} точек")
        logger.info(f"  Отброшено: {len(distances_mm) - len(filtered)} точек")

        return filtered

    @classmethod
    def _filter_points_by_profile_fallback(cls, distances_mm: List[int], profile, floor_level: int) -> List[int]:
        if not profile or not distances_mm:
            return distances_mm

        width_mm = profile.width_m * 1000
        depth_mm = profile.length_m * 1000
        height_mm = profile.height_m * 1000

        min_height = 30
        max_height = height_mm + 50

        min_dist = min(distances_mm)
        max_dist = max(distances_mm)
        center_dist = (min_dist + max_dist) / 2

        min_depth = center_dist - depth_mm / 2 - 50
        max_depth = center_dist + depth_mm / 2 + 50

        filtered = []
        for d in distances_mm:
            object_height = floor_level - d
            in_height = min_height <= object_height <= max_height
            in_depth = min_depth <= d <= max_depth

            if in_height and in_depth:
                filtered.append(d)

        return filtered

    @classmethod
    def _get_object_bounds(cls, distances_mm: List[int], profile, floor_level: int) -> Dict[str, Any]:
        if not profile:
            return {"error": "Нет профиля"}

        try:
            return profile.get_bounds(distances_mm, floor_level)
        except AttributeError:
            pass

        width_mm = profile.width_m * 1000
        depth_mm = profile.length_m * 1000
        height_mm = profile.height_m * 1000

        min_dist = min(distances_mm) if distances_mm else 0
        max_dist = max(distances_mm) if distances_mm else 0
        center_dist = (min_dist + max_dist) / 2 if distances_mm else 0

        return {
            "height": {
                "min": 30,
                "max": height_mm + 50,
                "from_floor": floor_level - min_dist if distances_mm else 0
            },
            "depth": {
                "min": center_dist - depth_mm / 2 - 50,
                "max": center_dist + depth_mm / 2 + 50,
                "center": center_dist
            },
            "spread": {
                "min": min_dist,
                "max": max_dist,
                "width": max_dist - min_dist
            },
            "profile": {
                "width_mm": width_mm,
                "depth_mm": depth_mm,
                "height_mm": height_mm
            }
        }

    @classmethod
    def _determine_status(cls, points_count: int, object_height: float,
                            profile: Any = None, spread: float = 0) -> Dict[str, Any]:
        if profile:
            is_empty, confidence = profile.is_empty(object_height, points_count)
            return {
                "is_empty": is_empty,
                "confidence": confidence,
                "status": "empty" if is_empty else "filled",
                "reason": f"По профилю {profile.name}: {'пусто' if is_empty else 'заполнено'} ({confidence}%)"
            }

        if points_count <= cls.EMPTY_POINTS_THRESHOLD:
            is_empty = True
            confidence = 90
            reason = f"Точек {points_count} <= {cls.EMPTY_POINTS_THRESHOLD} (пусто)"
        elif points_count >= cls.FILLED_POINTS_THRESHOLD:
            is_empty = False
            confidence = 85
            reason = f"Точек {points_count} >= {cls.FILLED_POINTS_THRESHOLD} (заполнено)"
        else:
            if points_count < 14:
                is_empty = True
                confidence = 70
                reason = f"Точек {points_count} в промежуточной зоне (скорее пусто)"
            else:
                is_empty = False
                confidence = 65
                reason = f"Точек {points_count} в промежуточной зоне (скорее заполнено)"

        return {
            "is_empty": is_empty,
            "confidence": confidence,
            "status": "empty" if is_empty else "filled",
            "reason": reason
        }


# Глобальный экземпляр для удобства
object_detector = ObjectDetector()