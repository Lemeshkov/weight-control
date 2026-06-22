# backend/services/empty_detector.py
"""
Детектор пустоты - использует ObjectDetector с новыми порогами
"""
import logging
from typing import Dict, Any
from services.object_detector import ObjectDetector

logger = logging.getLogger(__name__)

class EmptyDetector:
    """Определяет, пустой ли объект"""
    
    @classmethod
    def is_empty(cls, lidar_data: Dict[str, Any], mode: str = "auto") -> Dict[str, Any]:
        """
        Определяет, пустой ли объект или его нет
        
        Returns:
            {
                "is_empty": bool,
                "confidence": float,
                "reason": str,
                "object_status": str,
                "status_description": str,
                "points_count": int,
                "object_type": str,
                "height_mm": float
            }
        """
        distances = lidar_data.get("distances_mm", [])
        
        # ═══════════════════════════════════════════════════════════
        # 1. ПРОВЕРКА: ЕСТЬ ЛИ ДАННЫЕ ВООБЩЕ?
        # ═══════════════════════════════════════════════════════════
        if not distances:
            return {
                "is_empty": True,
                "confidence": 100,
                "reason": "Нет данных с лидара",
                "object_status": "no_data",
                "status_description": "❌ Нет данных с лидара",
                "points_count": 0,
                "object_type": "unknown",
                "height_mm": 0
            }
        
        # ═══════════════════════════════════════════════════════════
        # 2. ИСПОЛЬЗУЕМ ObjectDetector С НОВЫМИ ПОРОГАМИ
        # ═══════════════════════════════════════════════════════════
        result = ObjectDetector.process_scan(distances, {"mode": mode})
        
        # Получаем результат
        is_empty = result.get("is_empty", True)
        confidence = result.get("confidence", 80)
        object_type = result.get("object_type", "unknown")
        height_mm = result.get("object_height_mm", 0)
        points_count = result.get("points_count", len(distances))
        object_status = result.get("object_status", "unknown")
        status_text = result.get("status_text", "⏳ Статус неизвестен")
        
        # ═══════════════════════════════════════════════════════════
        # 3. ФОРМИРУЕМ ПОНЯТНЫЙ СТАТУС
        # ═══════════════════════════════════════════════════════════
        if object_status == "no_data":
            status_description = "❌ Нет данных с лидара"
        elif object_status == "no_object":
            status_description = "📭 Объект отсутствует"
        elif is_empty:
            if object_type == "box":
                status_description = f"📦 Коробка ПУСТАЯ ({points_count} точек)"
            elif object_type == "truck":
                status_description = f"🚛 Кузов ПУСТОЙ ({points_count} точек)"
            else:
                status_description = f"📭 Объект ПУСТОЙ ({points_count} точек)"
        else:
            if object_type == "box":
                status_description = f"📦 Коробка ЗАПОЛНЕНА ({points_count} точек)"
            elif object_type == "truck":
                status_description = f"🚛 Кузов ЗАПОЛНЕН ({points_count} точек)"
            else:
                status_description = f"📦 Объект ЗАПОЛНЕН ({points_count} точек)"
        
        return {
            "is_empty": is_empty,
            "confidence": confidence,
            "reason": result.get("reason", "Анализ завершен"),
            "object_status": object_status,
            "status_description": status_description,
            "points_count": points_count,
            "object_type": object_type,
            "height_mm": height_mm,
            "profile_name": result.get("profile_name", None),
            "profile_confidence": result.get("profile_confidence", 0),
            "dimensions": result.get("dimensions", {}),
            "box_type": result.get("box_type", "unknown"),
            "box_info": result.get("box_info", {}),
            "object_detected": result.get("object_detected", False),
        }
    
    @classmethod
    def get_empty_probability(cls, lidar_data: Dict) -> float:
        """Возвращает вероятность пустоты (0-100%)"""
        result = cls.is_empty(lidar_data)
        return result["confidence"]
    
    @classmethod
    def get_status_text(cls, lidar_data: Dict) -> str:
        """
        Возвращает понятный текст статуса для отображения
        """
        result = cls.is_empty(lidar_data)
        return result.get("status_description", "⏳ Статус неизвестен")
    
# # backend/services/empty_detector.py
# """
# Детектор пустоты
# """
# import logging
# from typing import Dict, Any
# from services.object_detector import ObjectDetector

# logger = logging.getLogger(__name__)

# class EmptyDetector:
#     """Определяет, пустой ли объект"""
    
#     # ═══════════════════════════════════════════════════════════
#     # ПАРАМЕТРЫ ДЕТЕКЦИИ
#     # ═══════════════════════════════════════════════════════════
#     MIN_POINTS_FOR_OBJECT = 10  # Минимум точек для объекта
#     MIN_HEIGHT_FOR_OBJECT = 20  # Минимальная высота объекта (мм)
#     MAX_HEIGHT_FOR_EMPTY = 50   # Максимальная высота для пустоты (мм)
    
#     @classmethod
#     def is_empty(cls, lidar_data: Dict[str, Any], mode: str = "auto") -> Dict[str, Any]:
#         """
#         Определяет, пустой ли объект или его нет
        
#         Returns:
#             {
#                 "is_empty": bool,          # True - пусто/нет объекта
#                 "confidence": float,       # Уверенность 0-100
#                 "reason": str,             # Причина
#                 "object_status": str,      # "no_object", "empty", "filled"
#                 "status_description": str, # Описание для отображения
#                 "points_count": int,
#                 "object_type": str,
#                 "height_mm": float
#             }
#         """
#         distances = lidar_data.get("distances_mm", [])
        
#         # ═══════════════════════════════════════════════════════════
#         # 1. ПРОВЕРКА: ЕСТЬ ЛИ ДАННЫЕ ВООБЩЕ?
#         # ═══════════════════════════════════════════════════════════
#         if not distances:
#             return {
#                 "is_empty": True,
#                 "confidence": 100,
#                 "reason": "Нет данных с лидара",
#                 "object_status": "no_data",
#                 "status_description": "❌ Нет данных с лидара",
#                 "points_count": 0,
#                 "object_type": "unknown",
#                 "height_mm": 0
#             }
        
#         # ═══════════════════════════════════════════════════════════
#         # 2. ПРОВЕРКА: ЕСТЬ ЛИ ОБЪЕКТ (по количеству точек)
#         # ═══════════════════════════════════════════════════════════
#         points_count = len(distances)
        
#         if points_count < cls.MIN_POINTS_FOR_OBJECT:
#             return {
#                 "is_empty": True,
#                 "confidence": 95,
#                 "reason": f"Слишком мало точек для объекта: {points_count}",
#                 "object_status": "no_object",
#                 "status_description": "📭 Объект отсутствует (мало точек)",
#                 "points_count": points_count,
#                 "object_type": "unknown",
#                 "height_mm": 0
#             }
        
#         # ═══════════════════════════════════════════════════════════
#         # 3. ПРОВЕРКА: ЕСТЬ ЛИ ВЫСОТА ОБЪЕКТА
#         # ═══════════════════════════════════════════════════════════
#         floor_level = lidar_data.get("floor_level_mm", max(distances) if distances else 0)
#         min_dist = min(distances)
#         object_height = floor_level - min_dist if floor_level > min_dist else 0
        
#         # Если высота меньше порога - нет объекта
#         if object_height < cls.MIN_HEIGHT_FOR_OBJECT:
#             return {
#                 "is_empty": True,
#                 "confidence": 90,
#                 "reason": f"Высота объекта слишком мала: {object_height:.1f}мм",
#                 "object_status": "no_object",
#                 "status_description": "📭 Объект отсутствует (низкая высота)",
#                 "points_count": points_count,
#                 "object_type": "unknown",
#                 "height_mm": object_height
#             }
        
#         # ═══════════════════════════════════════════════════════════
#         # 4. ПРОВЕРКА: ВСЕ ТОЧКИ - ЭТО ПОЛ/ФОН
#         # ═══════════════════════════════════════════════════════════
#         # Проверяем, не являются ли все точки полом
#         floor_points = [d for d in distances if d > floor_level - 100]
#         if len(floor_points) > points_count * 0.8:
#             return {
#                 "is_empty": True,
#                 "confidence": 92,
#                 "reason": "Обнаружен только пол, объект отсутствует",
#                 "object_status": "no_object",
#                 "status_description": "📭 Объект отсутствует (только пол)",
#                 "points_count": points_count,
#                 "object_type": "unknown",
#                 "height_mm": object_height
#             }
        
#         # ═══════════════════════════════════════════════════════════
#         # 5. ОПРЕДЕЛЯЕМ ПУСТОТУ КОРОБКИ/КУЗОВА
#         # ═══════════════════════════════════════════════════════════
#         # Используем ObjectDetector для анализа
#         result = ObjectDetector.process_scan(distances, {"mode": mode})
        
#         # Получаем результат
#         is_empty = result.get("is_empty", True)
#         confidence = result.get("confidence", 80)
#         object_type = result.get("object_type", "unknown")
#         height_mm = result.get("height_mm", object_height)
        
#         # ═══════════════════════════════════════════════════════════
#         # 6. ФОРМИРУЕМ ПОНЯТНЫЙ СТАТУС
#         # ═══════════════════════════════════════════════════════════
#         if is_empty:
#             object_status = "empty"
#             status_description = "📦 Коробка/кузов ПУСТОЙ"
#             if object_type == "box":
#                 status_description = "📦 Коробка ПУСТАЯ"
#             elif object_type == "truck":
#                 status_description = "🚛 Кузов ПУСТОЙ"
#         else:
#             object_status = "filled"
#             status_description = "📦 Коробка/кузов ЗАПОЛНЕН"
#             if object_type == "box":
#                 status_description = "📦 Коробка ЗАПОЛНЕНА"
#             elif object_type == "truck":
#                 status_description = "🚛 Кузов ЗАПОЛНЕН"
        
#         return {
#             "is_empty": is_empty,
#             "confidence": confidence,
#             "reason": result.get("reason", "Анализ завершен"),
#             "object_status": object_status,
#             "status_description": status_description,
#             "points_count": result.get("points_count", len(distances)),
#             "object_type": object_type,
#             "height_mm": height_mm,
#             "profile_name": result.get("profile_name", None),
#             "profile_confidence": result.get("profile_confidence", 0),
#             "dimensions": result.get("dimensions", {}),
#             "box_type": result.get("box_type", "unknown"),
#             "object_detected": result.get("object_detected", False),
#         }
    
#     @classmethod
#     def get_empty_probability(cls, lidar_data: Dict) -> float:
#         """Возвращает вероятность пустоты (0-100%)"""
#         result = cls.is_empty(lidar_data)
#         return result["confidence"]
    
#     @classmethod
#     def get_status_text(cls, lidar_data: Dict) -> str:
#         """
#         Возвращает понятный текст статуса для отображения
#         """
#         result = cls.is_empty(lidar_data)
        
#         # Получаем детали
#         points = result.get("points_count", 0)
#         height = result.get("height_mm", 0)
#         obj_type = result.get("object_type", "unknown")
#         status = result.get("object_status", "unknown")
        
#         # Формируем текст
#         if status == "no_data":
#             return "❌ Нет данных с лидара"
#         elif status == "no_object":
#             return f"📭 Объект отсутствует (точек: {points})"
#         elif status == "empty":
#             if obj_type == "box":
#                 return f"📦 Коробка ПУСТАЯ (высота: {height:.0f}мм)"
#             elif obj_type == "truck":
#                 return f"🚛 Кузов ПУСТОЙ (высота: {height:.0f}мм)"
#             else:
#                 return f"📭 Объект ПУСТОЙ (высота: {height:.0f}мм)"
#         else:  # filled
#             if obj_type == "box":
#                 return f"📦 Коробка ЗАПОЛНЕНА (высота: {height:.0f}мм)"
#             elif obj_type == "truck":
#                 return f"🚛 Кузов ЗАПОЛНЕН (высота: {height:.0f}мм)"
#             else:
#                 return f"📦 Объект ЗАПОЛНЕН (высота: {height:.0f}мм)"