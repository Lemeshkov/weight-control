

# backend/services/object_detector.py
"""
Детектор объектов - использует vehicle_profiles для определения типа и статуса
"""
import logging
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from collections import Counter
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

    @classmethod
    def process_scan(cls, distances_mm: List[int], params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Основной метод обработки скана
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

        logger.info(f" Объект: {points_count} точек, высота={object_height:.1f}мм, разброс={spread:.1f}мм")

        # ═══════════════════════════════════════════════════════════
        # ШАГ 4.5: ИЗМЕРЕНИЕ ШИРИНЫ КОРОБКИ
        # ═══════════════════════════════════════════════════════════
        width_info = cls._measure_box_width(object_points, floor_level)
        width_mm = width_info["width_mm"]
        
        logger.info(f"📏 Ширина коробки: {width_mm:.1f}мм (разброс: {spread:.1f}мм)")

        # ═══════════════════════════════════════════════════════════
        # ШАГ 5: ПОИСК ПРОФИЛЯ В БАЗЕ
        # ═══════════════════════════════════════════════════════════
        logger.info(f"[PROFILE] ВЫЗЫВАЕМ _find_matching_profile_enhanced для точек={len(object_points)}")

        match_result = cls._find_matching_profile_enhanced(
            object_points, 
            floor_level, 
            width_mm
        )
        profile = match_result.get("profile")
        profile_confidence = match_result.get("confidence", 0)

        logger.info(f"[PROFILE] РЕЗУЛЬТАТ: profile={profile.name if profile else 'None'}, confidence={profile_confidence}") 
        
        # ═══════════════════════════════════════════════════════════
        # ШАГ 5.5: ФИЛЬТРАЦИЯ ТОЧЕК ПО ПРОФИЛЮ
        # ═══════════════════════════════════════════════════════════
        if profile and profile_confidence > 30:
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
        # ШАГ 6: ОПРЕДЕЛЕНИЕ СТАТУСА
        # ═══════════════════════════════════════════════════════════
        status_result = cls._determine_status(
            points_count=points_count,
            object_height=object_height,
            profile=profile,
            spread=spread
        )

        # ═══════════════════════════════════════════════════════════
        # ШАГ 7: ПОЛУЧЕНИЕ ИНФОРМАЦИИ О КОРОБКЕ
        # ═══════════════════════════════════════════════════════════
        box_info = vehicle_profiles.get_box_info_from_profile(profile)

        if profile:
            box_info["profile_confidence"] = profile_confidence
            logger.info(f"🔍 Найден профиль: {profile.name} (уверенность: {profile_confidence}%)")

            if profile.vehicle_type == "box" and box_info.get("detected"):
                size_str = f"{box_info['size_cm']['width']}×{box_info['size_cm']['depth']}×{box_info['size_cm']['height']}"

                if status_result["is_empty"]:
                    status_text = f"📦 Коробка {box_info['box_label']} ({size_str}см) ПУСТАЯ"
                else:
                    status_text = f"📦 Коробка {box_info['box_label']} ({size_str}см) ЗАПОЛНЕНА"
            else:
                if status_result["is_empty"]:
                    status_text = f"🚛 {profile.name} - ПУСТОЙ"
                else:
                    status_text = f"🚛 {profile.name} - ЗАПОЛНЕН"
        else:
            if status_result["is_empty"]:
                status_text = "📭 Объект ПУСТОЙ"
            else:
                status_text = "📦 Объект ЗАПОЛНЕН"

            logger.warning(f"⚠️ Профиль не найден для точек={points_count}, разброс={spread}")

        # ═══════════════════════════════════════════════════════════
        # ШАГ 8: ФОРМИРОВАНИЕ РЕЗУЛЬТАТА
        # ═══════════════════════════════════════════════════════════
        return {
            "object_detected": True,
            "is_empty": status_result["is_empty"],
            "confidence": status_result["confidence"],
            "object_status": status_result["status"],
            "status_text": status_text,
            "object_type": profile.vehicle_type if profile else "unknown",
            "profile": profile.to_dict() if profile else None,
            "profile_confidence": profile_confidence,
            "box_info": box_info,
            "points_count": points_count,
            "object_height_mm": object_height,
            "floor_level_mm": floor_level,
            "spread_mm": spread,
            "width_mm": width_mm,
            "avg_distance_mm": avg_dist,
            "reason": status_result["reason"],
            "points": object_points,
            "all_points": valid_points,
        }

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
        if not distances_mm:
            return 2000

        floor_candidates = [d for d in distances_mm if 1500 <= d <= 3000]

        if floor_candidates:
            counter = Counter(floor_candidates)
            floor_level = counter.most_common(1)[0][0]
            logger.info(f"🏗️ Уровень пола (из диапазона 1500-3000): {floor_level} мм")
            return floor_level

        counter = Counter(distances_mm)
        floor_level = counter.most_common(1)[0][0]
        logger.info(f"🏗️ Уровень пола (fallback): {floor_level} мм")
        return floor_level

    @classmethod
    def _extract_object_points(cls, distances_mm: List[int], floor_level: int) -> List[int]:
        """
        Извлекает точки объекта, отсекая пол
        """
        if not distances_mm:
            return []

        # Пол - это самые дальние точки (ближе к floor_level)
        # Объект - это точки, которые значительно ближе к лидару

        # Находим порог для пола - точки в пределах 50мм от пола
        floor_threshold = 50  # мм

        # Точки объекта - те, что НЕ являются полом
        object_points = [d for d in distances_mm
                        if d < floor_level - floor_threshold]

        # Если точек объекта мало, возможно объект отсутствует
        if len(object_points) < cls.MIN_POINTS_FOR_OBJECT:
            # Возвращаем все точки (объект может быть низким)
            return distances_mm

        return object_points

    # ═══════════════════════════════════════════════════════════
    # МЕТОД ИЗМЕРЕНИЯ ШИРИНЫ
    # ═══════════════════════════════════════════════════════════

    @classmethod
    def _measure_box_width(cls, distances_mm: List[int], floor_level: int) -> Dict[str, float]:
        if not distances_mm or len(distances_mm) < 3:
            return {"width_mm": 0, "left_edge": 0, "right_edge": 0, "spread_mm": 0, "points_on_edges": 0}
        
        points = [(i, d) for i, d in enumerate(distances_mm) if d < floor_level - 50]
        
        if len(points) < 2:
            return {"width_mm": 0, "left_edge": 0, "right_edge": 0, "spread_mm": 0, "points_on_edges": 0}
        
        left_edge = None
        right_edge = None
        
        for i in range(1, len(points) - 1):
            prev_dist = points[i-1][1]
            curr_dist = points[i][1]
            next_dist = points[i+1][1]
            
            grad1 = abs(curr_dist - prev_dist)
            grad2 = abs(next_dist - curr_dist)
            
            if grad1 > 50 and grad2 > 50:
                if left_edge is None:
                    left_edge = points[i][0]
                elif right_edge is None and points[i][0] > left_edge + 3:
                    right_edge = points[i][0]
        
        if left_edge is None or right_edge is None:
            left_edge = points[0][0]
            right_edge = points[-1][0]
        
        left_dist = None
        right_dist = None
        for idx, dist in points:
            if idx == left_edge:
                left_dist = dist
            if idx == right_edge:
                right_dist = dist
        
        width_mm = abs(right_dist - left_dist) if left_dist and right_dist else 0
        
        points_on_edges = 0
        for idx, dist in points:
            if idx == left_edge or idx == right_edge:
                points_on_edges += 1
        
        return {
            "width_mm": round(width_mm, 1),
            "left_edge": left_edge,
            "right_edge": right_edge,
            "spread_mm": max(distances_mm) - min(distances_mm),
            "points_on_edges": points_on_edges
        }

    # ═══════════════════════════════════════════════════════════
    # МЕТОДЫ ИДЕНТИФИКАЦИИ С ВЕСАМИ
    # ═══════════════════════════════════════════════════════════

    @classmethod
    def _find_matching_profile_enhanced(cls, distances_mm: List[int], floor_level_mm: int, width_mm: float = 0) -> Dict[str, Any]:
        logger.info("[PROFILE] _find_matching_profile_enhanced ВЫЗВАН!")

        if not distances_mm or len(distances_mm) < 5:
            return {
                "profile": None,
                "confidence": 0,
                "reason": "Нет данных",
                "matches": []
            }

        points_count = len(distances_mm)
        spread = max(distances_mm) - min(distances_mm) if distances_mm else 0

        min_dist = min(distances_mm) if distances_mm else 0
        object_height = floor_level_mm - min_dist if floor_level_mm > min_dist else 0

        logger.info(f"[PROFILE] ПОИСК: точек={points_count}, разброс={spread}, высота={object_height:.0f}мм, ширина={width_mm:.1f}мм")
        logger.info(f"[PROFILE] Доступные профили: {[name for name in vehicle_profiles.profiles.keys()]}")

        matches = []

        for name, profile in vehicle_profiles.profiles.items():
            if profile.vehicle_type != "box":
                continue

            logger.info(f"  Проверяем профиль: {name}")

            score = 0
            reasons = []

            # 1. Количество точек → ВЕС 30
            p_min, p_max = profile.points_range
            if p_min <= points_count <= p_max:
                center = (p_min + p_max) / 2
                if p_max - p_min > 0:
                    closeness = 1 - abs(points_count - center) / ((p_max - p_min) / 2)
                    closeness = max(0, min(1, closeness))
                else:
                    closeness = 1.0
                score += 30 * closeness
                reasons.append(f"точек {points_count} в [{p_min}-{p_max}] (близость: {closeness:.2f})")
            else:
                if points_count < p_min:
                    score -= 15
                    reasons.append(f"точек {points_count} < {p_min} (-15)")
                else:
                    score -= 15
                    reasons.append(f"точек {points_count} > {p_max} (-15)")

            # 2. ШИРИНА → ВЕС 25
            if width_mm > 0:
                expected_width = profile.width_m * 1000
                width_diff = abs(width_mm - expected_width)
                
                if width_diff < 30:
                    score += 25
                    reasons.append(f"ширина {width_mm:.1f}мм ≈ {expected_width:.0f}мм (+25)")
                elif width_diff < 60:
                    score += 18
                    reasons.append(f"ширина {width_mm:.1f}мм близка к {expected_width:.0f}мм (+18)")
                elif width_diff < 100:
                    score += 10
                    reasons.append(f"ширина {width_mm:.1f}мм умеренно близка к {expected_width:.0f}мм (+10)")
                else:
                    score -= 10
                    reasons.append(f"ширина {width_mm:.1f}мм далека от {expected_width:.0f}мм (-10)")

            # 3. Разброс → ВЕС 25
            s_min, s_max = profile.spread_range
            if s_min <= spread <= s_max:
                center = (s_min + s_max) / 2
                if s_max - s_min > 0:
                    closeness = 1 - abs(spread - center) / ((s_max - s_min) / 2)
                    closeness = max(0, min(1, closeness))
                else:
                    closeness = 1.0
                score += 25 * closeness
                reasons.append(f"разброс {spread} в [{s_min}-{s_max}] (близость: {closeness:.2f})")
            else:
                if spread < s_min:
                    score -= 15
                    reasons.append(f"разброс {spread} < {s_min} (-15)")
                else:
                    score -= 15
                    reasons.append(f"разброс {spread} > {s_max} (-15)")

            # 4. Высота → ВЕС 20
            if object_height > 0:
                expected_height = profile.height_m * 1000
                height_diff = abs(object_height - expected_height)

                if height_diff < 30:
                    score += 20
                    reasons.append(f"высота {object_height:.0f}≈{expected_height:.0f} (+20)")
                elif height_diff < 60:
                    score += 15
                    reasons.append(f"высота {object_height:.0f}≈{expected_height:.0f} (+15)")
                elif height_diff < 100:
                    score += 10
                    reasons.append(f"высота {object_height:.0f}≈{expected_height:.0f} (+10)")
                else:
                    score -= 10
                    reasons.append(f"высота {object_height:.0f}≠{expected_height:.0f} (-10)")

            # БОНУС: если точек мало, но высота большая → это L
            if points_count < 10 and object_height > 400 and profile.box_type == "large":
                score += 15
                reasons.append(f"🔥 БОНУС: мало точек ({points_count}) + большая высота ({object_height:.0f}мм) → L (+15)")

            matches.append({
                "name": name,
                "profile": profile,
                "score": round(score, 1),
                "reasons": reasons,
                "vehicle_type": profile.vehicle_type,
                "object_height": object_height
            })

            logger.info(f"    score: {score:.1f}")

        matches.sort(key=lambda x: x["score"], reverse=True)
        best = matches[0] if matches else None

        logger.info(f"[PROFILE] ТОП-3 ПРОФИЛЯ ПО ВЕСАМ:")
        for i, m in enumerate(matches[:3]):
            logger.info(f"  #{i+1}: {m['name']} (score: {m['score']})")

        if best and len(matches) > 1:
            second_score = matches[1]["score"]
            if best["score"] - second_score < 10:
                logger.warning(f"⚠️ Маленький отрыв между профилями: {best['name']} ({best['score']}) vs {matches[1]['name']} ({second_score})")

        logger.info(f"[PROFILE] ЛУЧШИЙ: {best['name'] if best else 'НЕТ'} (score: {best['score'] if best else 0})")

        return {
            "profile": best["profile"] if best else None,
            "confidence": max(0, best["score"]) if best else 0,
            "reason": best["reasons"][0] if best and best["reasons"] else "нет совпадений",
            "matches": matches[:3],
            "object_height_mm": object_height
        }

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
        logger.info(f"  Отброшено: {len(distances_mm) - len(filtered)} точек (за пределами объекта)")

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