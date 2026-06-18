"""
Детектор объектов и фильтрация данных лидара
"""
import logging
import numpy as np
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger(__name__)

class ObjectDetector:
    """
    Обнаружение и анализ объектов на сцене
    """
    
    @classmethod
    def process_scan(cls, distances_mm: List[int], params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Основной метод обработки скана
        1. Фильтрация шума
        2. Удаление пола/фона
        3. Обнаружение объекта
        4. Анализ объекта
        """
        if not distances_mm:
            return {"error": "Нет данных"}
        
        params = params or {}
        
        # Шаг 1: Фильтрация шума
        filtered = cls._filter_noise(distances_mm)
        
        # Шаг 2: Находим уровень пола
        floor_level = cls._find_floor_level(filtered)
        
        # Шаг 3: Удаляем пол и фон
        object_points = cls._remove_floor(filtered, floor_level)
        
        # Шаг 4: Обнаруживаем объект(ы)
        objects = cls._detect_objects(object_points, floor_level)
        
        # Шаг 5: Выбираем основной объект
        main_object = cls._select_main_object(objects, params)
        
        # Шаг 6: Анализируем объект
        if main_object:
            analysis = cls._analyze_object(main_object, floor_level, params)
            return analysis
        else:
            return {
                "object_detected": False,
                "message": "Объект не обнаружен",
                "floor_level_mm": floor_level,
                "points_count": len(distances_mm)
            }
    
    @classmethod
    def _filter_noise(cls, distances_mm: List[int]) -> List[int]:
        """
        Удаление шумовых выбросов
        """
        if len(distances_mm) < 3:
            return distances_mm
        
        # Простая медианная фильтрация
        filtered = []
        window_size = 3
        
        for i in range(len(distances_mm)):
            start = max(0, i - window_size // 2)
            end = min(len(distances_mm), i + window_size // 2 + 1)
            window = distances_mm[start:end]
            filtered.append(int(np.median(window)))
        
        return filtered
    
    @classmethod
    def _find_floor_level(cls, distances_mm: List[int]) -> int:
        """
        Находит уровень пола (самые дальние точки)
        """
        if not distances_mm:
            return 2000  # значение по умолчанию
        
        # Уровень пола - это максимальное расстояние
        # Но отбрасываем выбросы (верхние 5%)
        sorted_dists = sorted(distances_mm)
        percentile_95 = sorted_dists[int(len(sorted_dists) * 0.95)]
        
        # Ищем самую частую дальнюю дистанцию
        from collections import Counter
        far_points = [d for d in distances_mm if d > percentile_95 - 50]
        
        if far_points:
            counter = Counter(far_points)
            floor_level = counter.most_common(1)[0][0]
        else:
            floor_level = max(distances_mm)
        
        return floor_level
    
    @classmethod
    def _remove_floor(cls, distances_mm: List[int], floor_level: int, threshold_mm: int = 30) -> List[int]:
        """
        Удаляет точки пола, оставляет только объекты
        """
        # Точки, которые значительно ближе пола - это объекты
        object_points = [d for d in distances_mm if d < floor_level - threshold_mm]
        return object_points
    
    @classmethod
    def _detect_objects(cls, points: List[int], floor_level: int) -> List[Dict]:
        """
        Обнаруживает отдельные объекты на сцене
        """
        if not points:
            return []
        
        objects = []
        current_object = []
        
        # Группируем точки по непрерывности
        for i, point in enumerate(points):
            if not current_object:
                current_object.append(point)
            else:
                # Если разрыв большой - новый объект
                if abs(point - current_object[-1]) > 100:  # 10 см разрыв
                    if current_object:
                        objects.append(cls._create_object(current_object, floor_level))
                    current_object = [point]
                else:
                    current_object.append(point)
        
        if current_object:
            objects.append(cls._create_object(current_object, floor_level))
        
        return objects
    
    @classmethod
    def _create_object(cls, points: List[int], floor_level: int) -> Dict:
        """
        Создает объект из списка точек
        """
        return {
            "points": points,
            "count": len(points),
            "min_distance": min(points),
            "max_distance": max(points),
            "avg_distance": sum(points) / len(points),
            "height_mm": floor_level - min(points) if points else 0,
            "width_mm": len(points)  # приблизительно
        }
    
    @classmethod
    def _select_main_object(cls, objects: List[Dict], params: Dict) -> Optional[Dict]:
        """
        Выбирает главный объект (самый большой по количеству точек)
        """
        if not objects:
            return None
        
        # Для тестирования коробки - ищем компактный объект
        if params.get("mode") == "test_box":
            # Коробка обычно компактная, с меньшим разбросом
            objects.sort(key=lambda x: x["width_mm"])
            return objects[0] if objects else None
        
        # Для грузовика - самый большой объект
        objects.sort(key=lambda x: x["count"], reverse=True)
        return objects[0]
    
    @classmethod
    def _analyze_object(cls, obj: Dict, floor_level: int, params: Dict) -> Dict:
        """
        Анализирует объект: пустой или заполненный
        """
        points_count = obj["count"]
        avg_height = obj["height_mm"]
        
        # Для тестовой коробки
        if params.get("mode") == "test_box":
            # Коробка считается:
            # - ПУСТОЙ: если высота меньше 3 см ИЛИ очень мало точек
            if avg_height < 30 or points_count < 10:
                return {
                    "object_detected": True,
                    "is_empty": True,
                    "confidence": 90,
                    "reason": f"Коробка пуста (высота {avg_height:.1f} мм, точек {points_count})",
                    "object_type": "box",
                    "height_mm": avg_height,
                    "points_count": points_count,
                    "floor_level_mm": floor_level
                }
            else:
                return {
                    "object_detected": True,
                    "is_empty": False,
                    "confidence": 90,
                    "reason": f"В коробке есть предметы (высота {avg_height:.1f} мм)",
                    "object_type": "box",
                    "height_mm": avg_height,
                    "points_count": points_count,
                    "floor_level_mm": floor_level
                }
        
        # Для грузовика с углем
        else:
            # Пороги для грузовика
            if points_count < 30:
                return {
                    "object_detected": True,
                    "is_empty": True,
                    "confidence": 85,
                    "reason": f"Кузов пуст (точек {points_count})",
                    "object_type": "truck",
                    "height_mm": avg_height,
                    "points_count": points_count,
                    "floor_level_mm": floor_level
                }
            elif avg_height < 50:  # меньше 5 см
                return {
                    "object_detected": True,
                    "is_empty": True,
                    "confidence": 75,
                    "reason": f"Низкая насыпь ({avg_height:.1f} мм)",
                    "object_type": "truck",
                    "height_mm": avg_height,
                    "points_count": points_count,
                    "floor_level_mm": floor_level
                }
            else:
                return {
                    "object_detected": True,
                    "is_empty": False,
                    "confidence": 85,
                    "reason": f"Кузов заполнен (высота {avg_height:.1f} мм)",
                    "object_type": "truck",
                    "height_mm": avg_height,
                    "points_count": points_count,
                    "floor_level_mm": floor_level
                }