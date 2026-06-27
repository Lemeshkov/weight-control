# backend/test_box_points.py
"""
Тестовый скрипт для измерения количества точек у разных коробок
"""
import socket
import time
import json
import os
from datetime import datetime
from collections import Counter
from typing import List, Dict, Any

# ═══════════════════════════════════════════════════════════
# НАСТРОЙКИ
# ═══════════════════════════════════════════════════════════
LIDAR_HOST = "192.168.1.101"
LIDAR_PORT = 2111
FIXED_FLOOR_LEVEL = 2786  # мм - расстояние до пола
FLOOR_THRESHOLD = 50      # мм - отсечение пола
WALL_MIN = 1000           # мм - начало стен
WALL_MAX = 2000           # мм - конец стен


def connect_lidar(host=LIDAR_HOST, port=LIDAR_PORT):
    """Подключение к лидару"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        print(f"✅ Подключен к {host}:{port}")
        
        sock.send(b"\x02sMN SetAccessMode 3 F4724744\x03")
        time.sleep(0.2)
        sock.send(b"\x02sMN Run\x03")
        time.sleep(0.2)
        
        return sock
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return None


def get_scan_data(sock):
    """Получение данных сканирования"""
    try:
        sock.send(b"\x02sRN LMDscandata\x03")
        time.sleep(0.3)
        response = sock.recv(65535)
        decoded = response.decode('utf-8', errors='ignore')
        decoded = decoded.strip('\x02\x03')
        return decoded
    except Exception as e:
        print(f"❌ Ошибка получения данных: {e}")
        return None


def parse_distances(raw_data):
    """Парсинг расстояний из DIST1 с пропуском служебных значений"""
    if not raw_data:
        return []
    
    parts = raw_data.split()
    distances = []
    
    for i, part in enumerate(parts):
        if part == "DIST1" and i + 1 < len(parts):
            j = i + 1
            
            # ⭐ ПРОПУСКАЕМ 4 СЛУЖЕБНЫХ ЗНАЧЕНИЯ
            skip_count = 0
            while j < len(parts) and skip_count < 4:
                j += 1
                skip_count += 1
            
            while j < len(parts) and parts[j] not in ["RSSI1", "RSSI2", "DIST2", "DEVICE"]:
                try:
                    hex_val = parts[j].strip()
                    if hex_val:
                        value = int(hex_val, 16)
                        if value > 0x7FFFFFFF:
                            value = value - 0x100000000
                        if 100 < value < 5000:
                            distances.append(value)
                except ValueError:
                    pass
                j += 1
            break
    
    return distances


def filter_angle(distances_mm, angle_deg=50):
    """Фильтрация угла"""
    if not distances_mm:
        return []
    
    total = len(distances_mm)
    keep = int(total * angle_deg / 190)
    if keep % 2 == 0:
        keep -= 1
    
    start = (total - keep) // 2
    end = start + keep
    
    return distances_mm[start:end]


def analyze_box(distances_mm, box_name, floor_level=FIXED_FLOOR_LEVEL):
    """
    Анализ данных коробки с фильтрацией стен
    """
    if not distances_mm:
        return None
    
    # ═══════════════════════════════════════════════════════════
    # ОТЛАДОЧНЫЙ ВЫВОД
    # ═══════════════════════════════════════════════════════════
    print(f"\n🔍 ОТЛАДКА: {box_name}")
    print(f"  Всего точек: {len(distances_mm)}")
    print(f"  МАКСИМАЛЬНОЕ расстояние: {max(distances_mm)} мм")
    print(f"  МИНИМАЛЬНОЕ расстояние: {min(distances_mm)} мм")
    print(f"  Среднее расстояние: {sum(distances_mm) / len(distances_mm):.1f} мм")
    
    # Фильтруем угол
    filtered = filter_angle(distances_mm, 50)
    print(f"  После фильтрации угла: {len(filtered)} точек")
    
    # Фильтруем по расстоянию
    valid = [d for d in filtered if 100 <= d <= 3000]
    print(f"  После фильтрации расстояний: {len(valid)} точек")
    
    # ═══════════════════════════════════════════════════════════
    # ⭐ ОТСЕКАЕМ ПОЛ И СТЕНЫ
    # ═══════════════════════════════════════════════════════════
    # 1. Отсекаем пол
    object_points = [d for d in valid if d < floor_level - FLOOR_THRESHOLD]
    
    # 2. Отсекаем стены (1000-2000 мм)
    filtered_points = []
    for d in object_points:
        if WALL_MIN <= d <= WALL_MAX:
            continue
        filtered_points.append(d)
    
    object_points = filtered_points
    
    print(f"  floor_level: {floor_level} мм")
    print(f"  FLOOR_THRESHOLD: {FLOOR_THRESHOLD} мм")
    print(f"  Порог отсечения: {floor_level - FLOOR_THRESHOLD} мм")
    print(f"  WALL_MIN: {WALL_MIN} мм, WALL_MAX: {WALL_MAX} мм")
    print(f"  Точек объекта (после фильтрации стен): {len(object_points)}")
    
    if not object_points:
        return {
            "box_name": box_name,
            "total_points": len(distances_mm),
            "filtered_points": len(filtered),
            "valid_points": len(valid),
            "object_points": 0,
            "min_dist": 0,
            "max_dist": 0,
            "avg_dist": 0,
            "height_mm": 0,
            "status": "❌ ОБЪЕКТ НЕ ОБНАРУЖЕН"
        }
    
    min_dist = min(object_points)
    max_dist = max(object_points)
    avg_dist = sum(object_points) / len(object_points)
    height_mm = floor_level - min_dist
    
    # Определяем статус
    if len(object_points) < 10:
        status = "📭 ПУСТО (мало точек)"
    elif len(object_points) < 17:
        status = "📭 ПУСТО (промежуточная зона)"
    else:
        status = "📦 ЗАПОЛНЕНО"
    
    return {
        "box_name": box_name,
        "total_points": len(distances_mm),
        "filtered_points": len(filtered),
        "valid_points": len(valid),
        "object_points": len(object_points),
        "min_dist": min_dist,
        "max_dist": max_dist,
        "avg_dist": round(avg_dist, 1),
        "height_mm": round(height_mm, 1),
        "spread_mm": max_dist - min_dist,
        "status": status,
        "sample_distances": object_points[:20]
    }


def print_result(result):
    """Красивый вывод результата"""
    if not result:
        return
    
    print("\n" + "="*70)
    print(f"📊 {result['box_name']}")
    print("="*70)
    print(f"  Всего точек: {result['total_points']}")
    print(f"  После фильтрации угла: {result['filtered_points']}")
    print(f"  После фильтрации расстояний: {result['valid_points']}")
    print(f"  Точек объекта (после фильтрации стен): {result['object_points']}")
    print(f"  Статус: {result['status']}")
    print(f"  Мин. расстояние: {result['min_dist']} мм")
    print(f"  Макс. расстояние: {result['max_dist']} мм")
    print(f"  Среднее: {result['avg_dist']} мм")
    print(f"  Высота: {result['height_mm']} мм")
    print(f"  Разброс: {result['spread_mm']} мм")
    print(f"  Пример точек: {result['sample_distances'][:10]}")


def interactive_test():
    """Интерактивный тест"""
    print("\n" + "="*70)
    print("🔬 ТЕСТ КОЛИЧЕСТВА ТОЧЕК КОРОБОК")
    print("="*70)
    print("\nПодготовьте коробки:")
    print("  1. ПУСТАЯ коробка S")
    print("  2. ЗАПОЛНЕННАЯ коробка S")
    print("  3. ПУСТАЯ коробка M")
    print("  4. ЗАПОЛНЕННАЯ коробка M")
    print("  5. ПУСТАЯ коробка L")
    print("  6. ЗАПОЛНЕННАЯ коробка L")
    print("  7. БЕЗ КОРОБКИ (фон/пол)")
    print("\nНажмите Enter для сканирования (или 'q' для выхода)")
    
    sock = connect_lidar()
    if not sock:
        return
    
    results = []
    scan_count = 0
    
    try:
        while True:
            cmd = input("\nСценарий (1-7 или q): ").strip()
            
            if cmd == 'q':
                break
            
            if cmd == '1':
                box_name = "Коробка S (20x31x25) - ПУСТАЯ"
            elif cmd == '2':
                box_name = "Коробка S (20x31x25) - ЗАПОЛНЕННАЯ"
            elif cmd == '3':
                box_name = "Коробка M (35x65x37) - ПУСТАЯ"
            elif cmd == '4':
                box_name = "Коробка M (35x65x37) - ЗАПОЛНЕННАЯ"
            elif cmd == '5':
                box_name = "Коробка L (40x60x60) - ПУСТАЯ"
            elif cmd == '6':
                box_name = "Коробка L (40x60x60) - ЗАПОЛНЕННАЯ"
            elif cmd == '7':
                box_name = "БЕЗ КОРОБКИ (фон)"
            else:
                print("❌ Неверный выбор. Введите 1-7 или q")
                continue
            
            scan_count += 1
            print(f"\n📡 Сканирование #{scan_count}: {box_name}...")
            
            raw_data = get_scan_data(sock)
            if not raw_data:
                print("❌ Ошибка получения данных")
                continue
            
            distances = parse_distances(raw_data)
            if not distances:
                print("❌ Нет данных")
                continue
            
            result = analyze_box(distances, box_name)
            if result:
                print_result(result)
                results.append(result)
            
            time.sleep(0.3)
    
    finally:
        sock.close()
        print("\n🔌 Отключено")
    
    # Сравнение результатов
    if len(results) >= 2:
        print("\n" + "="*70)
        print("📊 СРАВНЕНИЕ РЕЗУЛЬТАТОВ")
        print("="*70)
        print(f"\n{'Коробка':<30} {'Точки':<10} {'Высота':<10} {'Статус':<20}")
        print("-"*70)
        for r in results:
            print(f"{r['box_name']:<30} {r['object_points']:<10} {r['height_mm']:<10} {r['status']:<20}")
    
    print(f"\n✅ Выполнено сканирований: {scan_count}")


if __name__ == "__main__":
    interactive_test()