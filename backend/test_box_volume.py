# backend/test_box_volume.py
from services.lidar_client import LidarClient
import time

def test_box():
    client = LidarClient()
    
    if not client.connect():
        print("❌ Не удалось подключиться к лидару")
        return
    
    print("✅ Лидар подключен")
    print("\n" + "="*50)
    
    # 1. Проверка сырых данных
    print("\n1. ПОЛУЧЕНИЕ СЫРЫХ ДАННЫХ:")
    raw_data = client.get_scan_data()
    if raw_data:
        print(f"   Длина сырых данных: {len(raw_data)} байт")
        # Парсим без фильтрации
        parsed_raw = client.parse_scan_data(raw_data, filter_angle=False, separate_object=False)
        print(f"   Сырых точек: {len(parsed_raw.get('distances_mm', []))}")
    
    # 2. Проверка с фильтрацией угла
    print("\n2. ПОСЛЕ ФИЛЬТРАЦИИ УГЛА (70°):")
    parsed_angle = client.parse_scan_data(raw_data, filter_angle=True, separate_object=False)
    print(f"   Точек после фильтрации угла: {len(parsed_angle.get('distances_mm', []))}")
    
    # 3. Проверка с отделением объекта
    print("\n3. ПОСЛЕ ОТДЕЛЕНИЯ ОБЪЕКТА:")
    parsed_obj = client.parse_scan_data(raw_data, filter_angle=True, separate_object=True)
    distances = parsed_obj.get('distances_mm', [])
    print(f"   Точек объекта: {len(distances)}")
    
    if distances:
        print(f"   Уровень пола: {parsed_obj.get('floor_level_mm', 0)} мм")
        print(f"   Мин расстояние: {min(distances)} мм")
        print(f"   Макс расстояние: {max(distances)} мм")
        print(f"   Среднее: {sum(distances)/len(distances):.0f} мм")
        
        # Расчёт высоты объекта
        floor = parsed_obj.get('floor_level_mm', max(distances) + 500)
        heights = [floor - d for d in distances]
        print(f"\n📐 ВЫСОТА ОБЪЕКТА:")
        print(f"   Средняя: {sum(heights)/len(heights):.1f} мм")
        print(f"   Макс: {max(heights):.1f} мм")
        
        # Примерный объём для коробки 40x60 см
        width_cm = 40
        length_cm = 60
        avg_height_cm = sum(heights)/len(heights) / 10
        volume_liters = (width_cm * length_cm * avg_height_cm) / 1000
        print(f"\n📦 ПРИМЕРНЫЙ ОБЪЁМ (40x60см):")
        print(f"   Средняя высота: {avg_height_cm:.1f} см")
        print(f"   Объём: {volume_liters:.1f} литров")
    else:
        print("   ❌ Объект не обнаружен!")
        print("   Проверьте, что коробка находится под лидаром")
    
    client.disconnect()

if __name__ == "__main__":
    input("Поставьте коробку под лидар и нажмите Enter...")
    test_box()