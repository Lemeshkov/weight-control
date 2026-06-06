# backend/test_parsing_v2.py
import logging
from services.lidar_client import LidarClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test():
    client = LidarClient("192.168.0.1", 2111)
    
    if client.connect():
        print("✅ Подключено!\n")
        
        data = client.get_scan_data()
        if data:
            print("📊 Парсинг данных...\n")
            parsed = client.parse_scan_data(data)
            
            print("="*60)
            print("РЕЗУЛЬТАТ ПАРСИНГА")
            print("="*60)
            
            if parsed.get("valid"):
                print(f"\n📌 Общая информация:")
                print(f"  Номер скана: {parsed.get('scan_number', 'N/A')}")
                print(f"  Статус устройства: {parsed.get('device_status', 'N/A')}")
                print(f"  Количество точек: {parsed.get('points_count', 0)}")
                
                if parsed.get('distances_mm'):
                    print(f"\n📏 Расстояния:")
                    print(f"  Минимум: {parsed.get('min_distance_mm', 0)} мм ({parsed.get('min_distance_m', 0)} м)")
                    print(f"  Максимум: {parsed.get('max_distance_mm', 0)} мм ({parsed.get('max_distance_m', 0)} м)")
                    print(f"  Среднее: {parsed.get('avg_distance_mm', 0)} мм ({parsed.get('avg_distance_m', 0)} м)")
                    
                    # Показываем первые 10 расстояний
                    print(f"\n  Первые 10 расстояний:")
                    for i, dist in enumerate(parsed['distances_mm'][:10]):
                        print(f"    Точка {i:2}: {dist:4} мм ({dist/1000:.2f} м)")
                    
                    # Показываем последние 10 расстояний
                    if len(parsed['distances_mm']) > 10:
                        print(f"\n  Последние 10 расстояний:")
                        for i, dist in enumerate(parsed['distances_mm'][-10:]):
                            print(f"    Точка {len(parsed['distances_mm'])-10+i:2}: {dist:4} мм ({dist/1000:.2f} м)")
                else:
                    print("\n⚠️ Расстояния не найдены")
            else:
                print(f"\n❌ Ошибка: {parsed.get('error', 'Неизвестная ошибка')}")
        
        client.disconnect()
    else:
        print("❌ Не удалось подключиться")

if __name__ == "__main__":
    test()