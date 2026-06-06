# backend/test_parsing.py
import logging
from services.lidar_client import LidarClient

logging.basicConfig(level=logging.INFO)

def test():
    client = LidarClient("192.168.0.1", 2111)
    
    if client.connect():
        print("✅ Подключено!")
        
        data = client.get_scan_data()
        if data:
            print("\n📊 Парсинг данных...")
            parsed = client.parse_scan_data(data)
            
            print("\n=== РЕЗУЛЬТАТ ПАРСИНГА ===")
            print(f"Количество точек: {parsed.get('points_count', 0)}")
            print(f"Минимальное расстояние: {parsed.get('min_distance', 'N/A')} мм")
            print(f"Максимальное расстояние: {parsed.get('max_distance', 'N/A')} мм")
            print(f"Среднее расстояние: {parsed.get('avg_distance', 'N/A')} мм")
            
            if parsed.get('distances'):
                print(f"\nПервые 10 расстояний (мм):")
                for i, dist in enumerate(parsed['distances'][:10]):
                    print(f"  Точка {i}: {dist} мм ({dist/1000:.2f} м)")
        
        client.disconnect()

if __name__ == "__main__":
    test()