# backend/debug_lidar_data.py
import logging
from services.lidar_client import LidarClient

logging.basicConfig(level=logging.INFO)

def test():
    client = LidarClient("192.168.0.1", 2111)
    
    if client.connect():
        print("✅ Подключено!")
        
        data = client.get_scan_data()
        if data:
            print("\n=== СЫРЫЕ ДАННЫЕ ===")
            print(f"Длина: {len(data)} символов")
            print("\nВСЕ ДАННЫЕ:")
            print(data)
            print("\n" + "="*50)
            
            # Показываем позицию DIST1
            if "DIST1" in data:
                pos = data.find("DIST1")
                print(f"\nDIST1 найден на позиции {pos}")
                print(f"Контекст вокруг DIST1:")
                start = max(0, pos - 50)
                end = min(len(data), pos + 200)
                print(data[start:end])
        
        client.disconnect()

if __name__ == "__main__":
    test()