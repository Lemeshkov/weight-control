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
    # ⭐ КОНСТАНТЫ ФИЛЬТРАЦИИ (НА ОСНОВЕ ТЕСТА)
    # ═══════════════════════════════════════════════════════════
    MIN_VALID_DISTANCE = 100      # мм - минимальное реальное расстояние
    MAX_VALID_DISTANCE = 3000     # мм - максимальное реальное расстояние
    FLOOR_THRESHOLD = 150         # мм - отсечение пола (увеличено)
    MIN_POINTS_FOR_OBJECT = 5     # Минимум точек для объекта
    
    # ⭐ ПОРОГИ ОПРЕДЕЛЕНИЯ ПУСТОТЫ (ИЗ ТЕСТА)
    # no_object: 15 точек, empty: 24 точки, filled: 39 точек
    EMPTY_POINTS_THRESHOLD = 10   # Если <= 20 точек - пусто
    FILLED_POINTS_THRESHOLD = 17  # Если >= 30 точек - заполнено
    
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
        # ШАГ 2: ОПРЕДЕЛЕНИЕ УРОВНЯ ПОЛА (в диапазоне 1500-3000 мм)
        # ═══════════════════════════════════════════════════════════
        floor_level = cls._find_floor_level(valid_points)
        
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
        
        logger.info(f"📐 Объект: {points_count} точек, высота={object_height:.1f}мм, разброс={spread:.1f}мм")
        
        # ═══════════════════════════════════════════════════════════
        # ШАГ 5: ПОИСК ПРОФИЛЯ В БАЗЕ
        # ═══════════════════════════════════════════════════════════
        match_result = vehicle_profiles.find_matching_profile(object_points, floor_level)
        profile = match_result.get("profile")
        profile_confidence = match_result.get("confidence", 0)
        
        # ═══════════════════════════════════════════════════════════
        # ⭐ ШАГ 6: ОПРЕДЕЛЕНИЕ СТАТУСА ПО НОВЫМ ПОРОГАМ
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
        
        # Если профиль найден - обогащаем информацию
        if profile:
            box_info["profile_confidence"] = profile_confidence
            logger.info(f"🔍 Найден профиль: {profile.name} (уверенность: {profile_confidence}%)")
            
            # Если это коробка - обновляем status_text
            if profile.vehicle_type == "box" and box_info.get("detected"):
                size_str = f"{box_info['size_cm']['width']}×{box_info['size_cm']['depth']}×{box_info['size_cm']['height']}"
                
                if status_result["is_empty"]:
                    status_text = f"📦 Коробка {box_info['box_label']} ({size_str}см) ПУСТАЯ"
                else:
                    status_text = f"📦 Коробка {box_info['box_label']} ({size_str}см) ЗАПОЛНЕНА"
            else:
                # Грузовик или другой транспорт
                if status_result["is_empty"]:
                    status_text = f"🚛 {profile.name} - ПУСТОЙ"
                else:
                    status_text = f"🚛 {profile.name} - ЗАПОЛНЕН"
        else:
            # Профиль не найден - используем базовое определение
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
            "avg_distance_mm": avg_dist,
            "reason": status_result["reason"],
            "points": object_points,
            "all_points": valid_points,
        }
    
    @classmethod
    def _empty_result(cls, reason: str, status: str, floor_level: int = 0) -> Dict[str, Any]:
        """Возвращает результат для случая, когда объект не обнаружен"""
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
            "avg_distance_mm": 0,
            "reason": reason,
            "points": []
        }
    
    @classmethod
    def _filter_noise(cls, distances_mm: List[int]) -> List[int]:
        """Удаление шумовых выбросов медианным фильтром"""
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
        """Фильтрация по валидным расстояниям"""
        return [d for d in distances_mm 
                if cls.MIN_VALID_DISTANCE <= d <= cls.MAX_VALID_DISTANCE]
    
    @classmethod
    def _find_floor_level(cls, distances_mm: List[int]) -> int:
        """Находит уровень пола (самое частое расстояние в диапазоне 1500-3000)"""
        if not distances_mm:
            return 2000
        
        # ⭐ Ищем пол в диапазоне 1500-3000 мм (исключает мусор)
        floor_candidates = [d for d in distances_mm if 1500 <= d <= 3000]
        
        if floor_candidates:
            counter = Counter(floor_candidates)
            floor_level = counter.most_common(1)[0][0]
            logger.info(f"🏗️ Уровень пола (из диапазона 1500-3000): {floor_level} мм")
            return floor_level
        
        # Fallback: самое частое значение
        counter = Counter(distances_mm)
        floor_level = counter.most_common(1)[0][0]
        logger.info(f"🏗️ Уровень пола (fallback): {floor_level} мм")
        return floor_level
    
    @classmethod
    def _extract_object_points(cls, distances_mm: List[int], floor_level: int) -> List[int]:
        """Извлекает точки объекта (не пола)"""
        # Точки, которые ближе к лидару чем пол на FLOOR_THRESHOLD
        return [d for d in distances_mm 
                if d < floor_level - cls.FLOOR_THRESHOLD]
    
    @classmethod
    def _determine_status(cls, points_count: int, object_height: float, 
                         profile: Any = None, spread: float = 0) -> Dict[str, Any]:
        """
        ⭐ Определяет статус объекта (пусто/заполнено) ПО НОВЫМ ПОРОГАМ
        """
        # Если есть профиль - используем его логику
        if profile:
            # Используем метод is_empty из профиля
            is_empty, confidence = profile.is_empty(object_height, points_count)
            
            return {
                "is_empty": is_empty,
                "confidence": confidence,
                "status": "empty" if is_empty else "filled",
                "reason": f"По профилю {profile.name}: {'пусто' if is_empty else 'заполнено'} ({confidence}%)"
            }
        
        # ═══════════════════════════════════════════════════════════
        # ⭐ БЕЗ ПРОФИЛЯ - ИСПОЛЬЗУЕМ НОВЫЕ ПОРОГИ ИЗ ТЕСТА
        # ═══════════════════════════════════════════════════════════
        
        # 1. Если точек очень мало - пусто
        if points_count <= cls.EMPTY_POINTS_THRESHOLD:
            is_empty = True
            confidence = 90
            reason = f"Точек {points_count} <= {cls.EMPTY_POINTS_THRESHOLD} (пусто)"
        
        # 2. Если точек много - заполнено
        elif points_count >= cls.FILLED_POINTS_THRESHOLD:
            is_empty = False
            confidence = 85
            reason = f"Точек {points_count} >= {cls.FILLED_POINTS_THRESHOLD} (заполнено)"
        
        # 3. Промежуточная зона (20-30 точек)
        else:
            # Анализируем дополнительно
            if points_count < 25:
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
