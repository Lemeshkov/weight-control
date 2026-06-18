"""
Тестирование детектора объектов
"""
from services.lidar_client import LidarClient
from services.object_detector import ObjectDetector
from services.empty_detector import EmptyDetector
import time

def test_detector():
    client = LidarClient()
    if not client.connect():
        print("❌ Не удалось подключиться")
        return
    
    print("🔍 Тестирование архитектуры: Фильтрация → Объект → Анализ")
    print("=" * 60)
    
    # Тест 1: Пустая коробка
    input("\n📦 1. Уберите всё из коробки и нажмите Enter...")
    raw_data = client.get_scan_data()
    parsed = client.parse_scan_data(raw_data, mode="test_box")
    
    print(f"\n📊 РЕЗУЛЬТАТ:")
    print(f"   Объект обнаружен: {parsed.get('object_detected')}")
    print(f"   Тип объекта: {parsed.get('object_type')}")
    print(f"   Пустой: {parsed.get('is_empty')}")
    print(f"   Уверенность: {parsed.get('empty_confidence')}%")
    print(f"   Причина: {parsed.get('empty_reason')}")
    print(f"   Высота объекта: {parsed.get('object_height_mm')} мм")
    print(f"   Уровень пола: {parsed.get('floor_level_mm')} мм")
    print(f"   Всего точек: {parsed.get('points_count')}")
    
    # Тест 2: Коробка с предметом
    input("\n\n📦 2. Положите предмет в коробку и нажмите Enter...")
    raw_data = client.get_scan_data()
    parsed = client.parse_scan_data(raw_data, mode="test_box")
    
    print(f"\n📊 РЕЗУЛЬТАТ:")
    print(f"   Объект обнаружен: {parsed.get('object_detected')}")
    print(f"   Тип объекта: {parsed.get('object_type')}")
    print(f"   Пустой: {parsed.get('is_empty')}")
    print(f"   Уверенность: {parsed.get('empty_confidence')}%")
    print(f"   Причина: {parsed.get('empty_reason')}")
    print(f"   Высота объекта: {parsed.get('object_height_mm')} мм")
    print(f"   Уровень пола: {parsed.get('floor_level_mm')} мм")
    
    client.disconnect()

if __name__ == "__main__":
    test_detector()