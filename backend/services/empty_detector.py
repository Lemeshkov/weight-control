"""
Детектор пустоты (обертка над ObjectDetector)
"""
import logging
from typing import Dict, Any
from services.object_detector import ObjectDetector

logger = logging.getLogger(__name__)

class EmptyDetector:
    """
    Определяет, пустой ли объект (коробка/кузов)
    """
    
    @classmethod
    def is_empty(cls, lidar_data: Dict[str, Any], mode: str = "auto") -> Dict[str, Any]:
        """
        Определяет, пустой ли объект
        
        Параметры:
        - lidar_data: данные с лидара (должны содержать distances_mm)
        - mode: "auto", "test_box", "truck"
        """
        distances = lidar_data.get("distances_mm", [])
        
        if not distances:
            return {
                "is_empty": True,
                "confidence": 100,
                "reason": "Нет данных",
                "points_count": 0,
                "object_type": "unknown"
            }
        
        # Если в данных уже есть результат анализа, используем его
        if "is_empty" in lidar_data and "empty_confidence" in lidar_data:
            logger.info("Использую готовый результат анализа из данных")
            return {
                "is_empty": lidar_data.get("is_empty", True),
                "confidence": lidar_data.get("empty_confidence", 80),
                "reason": lidar_data.get("empty_reason", "Анализ выполнен"),
                "points_count": lidar_data.get("points_count", len(distances)),
                "object_type": lidar_data.get("object_type", "unknown"),
                "height_mm": lidar_data.get("object_height_mm", 0)
            }
        
        # Автоопределение режима по количеству точек
        if mode == "auto":
            points_count = len(distances)
            if points_count < 50:
                mode = "test_box"
                logger.info(f"Автоопределение: режим TEST_BOX (точек: {points_count})")
            else:
                mode = "truck"
                logger.info(f"Автоопределение: режим TRUCK (точек: {points_count})")
        
        # Используем ObjectDetector для анализа
        result = ObjectDetector.process_scan(distances, {"mode": mode})
        
        return {
            "is_empty": result.get("is_empty", True),
            "confidence": result.get("confidence", 80),
            "reason": result.get("reason", "Анализ завершен"),
            "points_count": result.get("points_count", len(distances)),
            "object_type": result.get("object_type", "unknown"),
            "height_mm": result.get("height_mm", 0)
        }
    
    @classmethod
    def get_empty_probability(cls, lidar_data: Dict) -> float:
        """Возвращает вероятность пустоты (0-100%)"""
        result = cls.is_empty(lidar_data)
        return result["confidence"]