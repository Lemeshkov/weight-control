# backend/test_lidar_filter.py
"""
Тест фильтрации данных лидара
Сравнивает сырые данные и отфильтрованные
"""
import socket
import time
import json
from datetime import datetime
from collections import Counter

def get_raw_scan_data(host="192.168.1.101", port=2111):
    """Получить сырые данные с лидара"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        print(f"✅ Подключен к {host}:{port}")
        
        sock.send(b"\x02sMN SetAccessMode 3 F4724744\x03")
        time.sleep(0.2)
        sock.send(b"\x02sMN Run\x03")
        time.sleep(0.2)
        
        sock.send(b"\x02sRN LMDscandata\x03")
        time.sleep(0.3)
        response = sock.recv(65535)
        decoded = response.decode('utf-8', errors='ignore')
        decoded = decoded.strip('\x02\x03')
        
        sock.close()
        return decoded
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None

def parse_distances(raw_data):
    """Парсинг расстояний из DIST1 с ПРАВИЛЬНОЙ фильтрацией"""
    if not raw_data:
        return []
    
    parts = raw_data.split()
    distances_raw = []  # Все расстояния (для анализа)
    distances_filtered = []  # Только валидные
    
    for i, part in enumerate(parts):
        if part == "DIST1" and i + 1 < len(parts):
            j = i + 1
            while j < len(parts) and parts[j] not in ["RSSI1", "RSSI2", "DIST2", "DEVICE"]:
                try:
                    hex_val = parts[j].strip()
                    if hex_val:
                        value = int(hex_val, 16)
                        if value > 0x7FFFFFFF:
                            value = value - 0x100000000
                        
                        distances_raw.append(value)
                        
                        # ⭐ ПРАВИЛЬНАЯ ФИЛЬТРАЦИЯ:
                        # 1. Только положительные значения
                        # 2. Не слишком большие (макс 5000 мм)
                        # 3. Не слишком маленькие (мин 100 мм)
                        if 100 < value < 5000:
                            distances_filtered.append(value)
                            
                except ValueError:
                    pass
                j += 1
            break
    
    return distances_raw, distances_filtered

def analyze_with_filter(distances_raw, distances_filtered, name="Данные"):
    """Анализ сырых и отфильтрованных данных"""
    print(f"\n{'='*70}")
    print(f"📊 АНАЛИЗ {name}")
    print(f"{'='*70}")
    
    # Сырые данные
    print(f"\n📌 СЫРЫЕ ДАННЫЕ (до фильтрации):")
    print(f"  Всего точек: {len(distances_raw)}")
    if distances_raw:
        print(f"  Мин: {min(distances_raw)} мм")
        print(f"  Макс: {max(distances_raw)} мм")
        print(f"  Среднее: {sum(distances_raw)/len(distances_raw):.1f} мм")
    
    # Отфильтрованные данные
    print(f"\n📌 ОТФИЛЬТРОВАННЫЕ ДАННЫЕ (после фильтрации):")
    print(f"  Всего точек: {len(distances_filtered)}")
    if distances_filtered:
        print(f"  Мин: {min(distances_filtered)} мм")
        print(f"  Макс: {max(distances_filtered)} мм")
        print(f"  Среднее: {sum(distances_filtered)/len(distances_filtered):.1f} мм")
        
        # Находим уровень пола (самое частое значение)
        counter = Counter(distances_filtered)
        if counter:
            floor_level = counter.most_common(1)[0][0]
            floor_count = counter.most_common(1)[0][1]
            print(f"\n🏗️ УРОВЕНЬ ПОЛА:")
            print(f"  {floor_level} мм ({floor_count} раз)")
            
            # Точки объекта (ближе к лидару)
            object_threshold = 100  # мм от пола
            object_points = [d for d in distances_filtered if d < floor_level - object_threshold]
            
            print(f"\n📦 ТОЧКИ ОБЪЕКТА:")
            print(f"  Количество: {len(object_points)}")
            if object_points:
                print(f"  Мин: {min(object_points)} мм")
                print(f"  Макс: {max(object_points)} мм")
                print(f"  Среднее: {sum(object_points)/len(object_points):.1f} мм")
                
                # Частые значения
                obj_counter = Counter(object_points)
                obj_common = obj_counter.most_common(5)
                print(f"  Частые: {obj_common}")
            
            return {
                "filtered_count": len(distances_filtered),
                "floor_level": floor_level,
                "object_count": len(object_points)
            }
    
    return None

def main():
    print("\n🔬 ТЕСТ ФИЛЬТРАЦИИ ЛИДАРА")
    print("="*70)
    print("\nПодготовьте:")
    print("  1. БЕЗ КОРОБКИ (пустое поле)")
    print("  2. ПУСТАЯ КОРОБКА")
    print("  3. ПОЛНАЯ КОРОБКА")
    print("\nНажмите Enter для сканирования (или 'q' для выхода)")
    
    results = []
    scenarios = []
    
    while True:
        cmd = input("\nСценарий (1/2/3/q): ").strip()
        
        if cmd == 'q':
            break
        elif cmd == '1':
            scenario = "no_object"
        elif cmd == '2':
            scenario = "box_empty"
        elif cmd == '3':
            scenario = "box_filled"
        else:
            print("❌ Введите 1, 2, 3 или q")
            continue
        
        print(f"\n📡 Сканирование: {scenario}...")
        raw_data = get_raw_scan_data()
        
        if raw_data:
            distances_raw, distances_filtered = parse_distances(raw_data)
            result = analyze_with_filter(distances_raw, distances_filtered, scenario.upper())
            
            if result:
                results.append({
                    "scenario": scenario,
                    "object_count": result["object_count"],
                    "floor_level": result["floor_level"],
                    "filtered_count": result["filtered_count"]
                })
                scenarios.append(scenario)
    
    # ═══════════════════════════════════════════════════════════
    # СРАВНЕНИЕ
    # ═══════════════════════════════════════════════════════════
    if len(results) >= 2:
        print("\n" + "="*70)
        print("📊 СРАВНЕНИЕ СЦЕНАРИЕВ (ОТФИЛЬТРОВАННЫЕ ДАННЫЕ)")
        print("="*70)
        
        for r in results:
            print(f"\n{r['scenario']}:")
            print(f"  Отфильтрованных точек: {r['filtered_count']}")
            print(f"  Уровень пола: {r['floor_level']} мм")
            print(f"  Точек объекта: {r['object_count']}")
        
        # Рекомендации
        print("\n" + "="*70)
        print("💡 РЕКОМЕНДАЦИИ ПО НАСТРОЙКЕ")
        print("="*70)
        
        # Находим среднее количество точек объекта
        obj_counts = [r['object_count'] for r in results]
        avg_obj = sum(obj_counts) / len(obj_counts)
        
        print(f"\n📦 Среднее количество точек объекта: {avg_obj:.0f}")
        
        if avg_obj < 10:
            print("  ⚠️ Очень мало точек! Возможно объект отсутствует")
            print(f"  Рекомендуется: EMPTY_POINTS_THRESHOLD = {int(avg_obj + 5)}")
        elif avg_obj < 30:
            print("  📦 Вероятно пустая коробка")
            print(f"  Рекомендуется: EMPTY_POINTS_THRESHOLD = {int(avg_obj - 5)}")
            print(f"  Рекомендуется: FILLED_POINTS_THRESHOLD = {int(avg_obj + 10)}")
        else:
            print("  📦 Вероятно полная коробка")
            print(f"  Рекомендуется: EMPTY_POINTS_THRESHOLD = {int(avg_obj - 15)}")
            print(f"  Рекомендуется: FILLED_POINTS_THRESHOLD = {int(avg_obj - 5)}")
        
        print(f"\n  self.FLOOR_THRESHOLD = 100  # мм от пола")
        print(f"  self.MIN_VALID_DISTANCE = 100  # мм")
        print(f"  self.MAX_VALID_DISTANCE = 3000  # мм")
        
        # Сохраняем результаты
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"filter_test_{timestamp}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": timestamp,
                "results": results,
                "recommendations": {
                    "avg_object_points": avg_obj,
                    "floor_threshold": 100,
                    "min_distance": 100,
                    "max_distance": 3000
                }
            }, f, indent=2)
        
        print(f"\n✅ Результаты сохранены в {filename}")
    
    print("\n✅ Тест завершен")

if __name__ == "__main__":
    main()