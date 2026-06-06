# backend/test_final_parse.py
import logging
from services.lidar_client import LidarClient
import json

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test():
    client = LidarClient("192.168.0.1", 2111)
    
    if client.connect():
        print("\n✅ Подключено!\n")
        
        for scan_num in range(3):  # Делаем 3 скана для проверки
            print(f"\n{'='*60}")
            print(f"СКАН #{scan_num + 1}")
            print(f"{'='*60}")
            
            data = client.get_scan_data()
            if data:
                parsed = client.parse_scan_data(data)
                
                if parsed.get("valid"):
                    print(f"\n📊 Статистика:")
                    print(f"  Количество точек: {parsed.get('points_count', 0)}")
                    
                    if parsed.get('distances_mm'):
                        print(f"\n📏 Расстояния:")
                        print(f"  Мин: {parsed.get('min_distance_mm', 0)} мм ({parsed.get('min_distance_m', 0)} м)")
                        print(f"  Макс: {parsed.get('max_distance_mm', 0)} мм ({parsed.get('max_distance_m', 0)} м)")
                        print(f"  Сред: {parsed.get('avg_distance_mm', 0)} мм ({parsed.get('avg_distance_m', 0)} м)")
                        
                        # Показываем первые 10 расстояний
                        print(f"\n  Первые 10 расстояний:")
                        for i, dist in enumerate(parsed['distances_mm'][:10]):
                            print(f"    Точка {i:2}: {dist:4} мм ({dist/1000:.2f} м)")
                    
                    if parsed.get('intensities'):
                        print(f"\n💡 Интенсивность (первые 10):")
                        for i, intens in enumerate(parsed['intensities'][:10]):
                            print(f"    Точка {i:2}: {intens}")
                    
                    # Сохраняем в JSON для отладки
                    debug_info = {
                        "points_count": parsed.get('points_count'),
                        "first_10_distances": parsed.get('distances_mm', [])[:10],
                        "first_10_intensities": parsed.get('intensities', [])[:10]
                    }
                    print(f"\n📋 Debug info: {json.dumps(debug_info, indent=2)}")
                else:
                    print(f"\n❌ Ошибка парсинга: {parsed.get('error')}")
            
            print()
            time.sleep(1)  # Пауза между сканами
        
        client.disconnect()
    else:
        print("❌ Не удалось подключиться")

if __name__ == "__main__":
    import time
    test()