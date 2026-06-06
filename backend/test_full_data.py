# backend/test_full_data.py
import logging
from services.lidar_client import LidarClient

logging.basicConfig(level=logging.INFO)

def test():
    client = LidarClient("192.168.0.1", 2111)
    
    if client.connect():
        data = client.get_scan_data()
        if data:
            print("\n" + "="*80)
            print("ПОЛНЫЙ АНАЛИЗ ДАННЫХ")
            print("="*80)
            
            # Разбиваем на части
            parts = data.split()
            
            print(f"\nВсего частей: {len(parts)}")
            print("\nВсе части с индексами:")
            for idx, part in enumerate(parts[:50]):  # Первые 50 частей
                if part == "DIST1":
                    print(f"[{idx:3}] *** {part} *** (ДАННЫЕ РАССТОЯНИЙ)")
                elif part == "RSSI1":
                    print(f"[{idx:3}] *** {part} *** (ИНТЕНСИВНОСТЬ)")
                else:
                    preview = part[:50] + "..." if len(part) > 50 else part
                    print(f"[{idx:3}] {preview}")
            
            # Находим DIST1 и анализируем
            for i, part in enumerate(parts):
                if part == "DIST1" and i + 1 < len(parts):
                    print(f"\n{'='*80}")
                    print(f"DIST1 найден! Данные после него:")
                    print(f"{'='*80}")
                    
                    dist_data = parts[i + 1]
                    print(f"\nДлина строки: {len(dist_data)} символов")
                    print(f"Строка: {dist_data[:200]}...")
                    
                    # Пробуем интерпретировать как последовательность байт
                    print(f"\nИнтерпретация как байты (2 символа = 1 байт):")
                    byte_values = []
                    for j in range(0, min(100, len(dist_data)), 2):
                        if j + 2 <= len(dist_data):
                            byte_hex = dist_data[j:j+2]
                            try:
                                byte_val = int(byte_hex, 16)
                                byte_values.append(byte_val)
                                print(f"  {byte_hex} -> {byte_val:3d}", end=" ")
                                if (j//2 + 1) % 10 == 0:
                                    print()
                            except:
                                print(f"  {byte_hex} -> ?", end=" ")
                    
                    # Если есть значения, показываем расстояния
                    if byte_values:
                        print(f"\n\nВозможные расстояния (в мм):")
                        for idx, val in enumerate(byte_values[:20]):
                            if 10 < val < 8000:  # 1cm - 8m
                                print(f"  Точка {idx:2}: {val:3} мм ({val/1000:.2f} м)")
                    
                    break
        
        client.disconnect()

if __name__ == "__main__":
    test()