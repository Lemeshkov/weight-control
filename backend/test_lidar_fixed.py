# backend/test_lidar_fixed.py
import sys
import time
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

from services.lidar_client import LidarClient

def test():
    print("🔧 Тестирование подключения к лидару...")
    client = LidarClient("192.168.0.1", 2111)
    
    print("📡 Подключение...")
    if client.connect():
        print("✅ Подключено успешно!")
        
        print("\n📊 Запрос данных сканирования...")
        data = client.get_scan_data()
        
        if data:
            print(f"\n✅ Данные получены! Размер: {len(data)} байт")
            print("\n🔍 Первые 300 символов:")
            print("-" * 50)
            print(data[:300])
            print("-" * 50)
            
            # Проверяем наличие данных расстояний
            if "DIST1" in data:
                print("\n✅ Найдены данные расстояний (DIST1)")
                # Извлекаем первые несколько расстояний
                import re
                match = re.search(r'DIST1\s+([\d\s]+?)(?:\s+\w+|$)', data)
                if match:
                    distances = match.group(1).strip().split()
                    print(f"📏 Количество точек: {len(distances)}")
                    print(f"📏 Первые 10 расстояний: {distances[:10]} (значения в мм)")
            else:
                print("\n⚠️ Данные DIST1 не найдены")
        else:
            print("❌ Не удалось получить данные")
    else:
        print("❌ Не удалось подключиться")
    
    client.disconnect()

if __name__ == "__main__":
    test()