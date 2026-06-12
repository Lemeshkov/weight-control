# backend/services/empty_detector.py
"""
Детектор пустого кузова/коробки
"""

import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class EmptyDetector:
    """
    Определяет, пустой ли объект (коробка/кузов)
    """
    
    @classmethod
    def is_empty(cls, lidar_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Определяет, пустой ли объект по данным лидара
        
        Параметры:
        - lidar_data: результат parse_scan_data
        
        Возвращает:
        - словарь с решением и метриками
        """
        distances = lidar_data.get("distances_mm", [])
        points_count = lidar_data.get("points_count", 0)
        floor_level = lidar_data.get("floor_level_mm", 0)
        
        # 1. Если точек очень мало - скорее всего пусто
        if points_count < 10:
            return {
                "is_empty": True,
                "confidence": 85,
                "reason": f"Маловато точек: {points_count}",
                "points_count": points_count
            }
        
        # 2. Анализируем разброс высот
        if distances:
            max_dist = max(distances)
            min_dist = min(distances)
            spread = max_dist - min_dist
            
            # Если разброс меньше 50 мм - поверхность ровная (возможно дно)
            if spread < 50:
                return {
                    "is_empty": True,
                    "confidence": 70,
                    "reason": f"Ровная поверхность (разброс {spread} мм)",
                    "points_count": points_count
                }
        
        # 3. Сравниваем с эталоном пустого объекта
        empty_threshold = cls._get_empty_threshold(lidar_data)
        if points_count < empty_threshold:
            return {
                "is_empty": True,
                "confidence": 75,
                "reason": f"Точек меньше порога ({points_count} < {empty_threshold})",
                "points_count": points_count
            }
        
        # 4. По умолчанию - не пусто
        return {
            "is_empty": False,
            "confidence": 80,
            "reason": f"Обнаружен объект ({points_count} точек)",
            "points_count": points_count
        }
    
    @classmethod
    def _get_empty_threshold(cls, data: Dict) -> int:
        """
        Возвращает порог точек для определения пустоты
        В зависимости от типа объекта (коробка/грузовик)
        """
        # Для коробки (тест)
        if data.get("type") == "box":
            return 15
        # Для грузовика
        return 50
    
    @classmethod
    def get_empty_probability(cls, lidar_data: Dict) -> float:
        """
        Возвращает вероятность того, что объект пустой (0-100%)
        """
        distances = lidar_data.get("distances_mm", [])
        points_count = lidar_data.get("points_count", 0)
        
        if points_count == 0:
            return 100.0
        
        # Чем меньше точек, тем выше вероятность пустоты
        max_points = 150  # максимальное ожидаемое количество точек для заполненного
        probability = max(0, 100 - (points_count / max_points * 100))
        
        # Корректировка на основе разброса высот
        if distances and len(distances) > 5:
            spread = max(distances) - min(distances)
            if spread < 50:  # очень ровно
                probability = min(100, probability + 20)
        
        return round(probability, 1)