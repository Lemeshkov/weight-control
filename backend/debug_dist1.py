# backend/debug_dist1.py
import logging
from services.lidar_client import LidarClient

logging.basicConfig(level=logging.INFO)

def test():
    client = LidarClient("192.168.0.1", 2111)
    
    if client.connect():
        data = client.get_scan_data()
        if data:
            # Находим DIST1
            if "DIST1" in data:
                parts = data.split()
                for i, part in enumerate(parts):
                    if part == "DIST1":
                        print(f"\n=== АНАЛИЗ DIST1 ===")
                        print(f"Позиция DIST1: {i}")
                        
                        # Данные после DIST1
                        dist_data = parts[i + 1]
                        print(f"\nСырые данные DIST1:")
                        print(f"Длина: {len(dist_data)} символов")
                        print(f"Содержимое: {dist_data}")
                        
                        # Показываем в разных форматах
                        print(f"\nРазбивка по 2 символа (байты):")
                        for j in range(0, min(100, len(dist_data)), 2):
                            if j + 2 <= len(dist_data):
                                byte_val = dist_data[j:j+2]
                                try:
                                    num = int(byte_val, 16)
                                    print(f"  {byte_val} -> {num:3d}", end=" ")
                                    if (j//2 + 1) % 10 == 0:
                                        print()
                                except:
                                    print(f"  {byte_val} -> ?", end=" ")
                        print("\n")
                        
                        # Показываем разбивку по 4 символа (слова)
                        print(f"Разбивка по 4 символа (16-bit):")
                        for j in range(0, min(200, len(dist_data)), 4):
                            if j + 4 <= len(dist_data):
                                word_val = dist_data[j:j+4]
                                try:
                                    num = int(word_val, 16)
                                    print(f"  {word_val} -> {num:5d} мм ({num/1000:.2f} м)")
                                except:
                                    print(f"  {word_val} -> ?")
                        break
        
        client.disconnect()

if __name__ == "__main__":
    test()