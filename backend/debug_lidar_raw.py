# backend/debug_lidar_raw.py
"""
Скрипт для анализа сырых данных лидара
Записывает данные в файл для последующего анализа
"""
import socket
import time
import json
import os
from datetime import datetime

def get_raw_scan_data(host="192.168.1.101", port=2111):
    """Получить сырые данные с лидара"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        print(f"✅ Подключен к {host}:{port}")
        
        # Отправляем команды
        sock.send(b"\x02sMN SetAccessMode 3 F4724744\x03")
        time.sleep(0.2)
        sock.send(b"\x02sMN Run\x03")
        time.sleep(0.2)
        
        # Получаем данные
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
    """Парсит только расстояния из сырых данных"""
    if not raw_data:
        return []
    
    parts = raw_data.split()
    distances = []
    
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
                        if 0 <= value <= 50000:
                            distances.append(value)
                except ValueError:
                    pass
                j += 1
            break
    
    return distances

def analyze_distances(distances):
    """Анализирует расстояния и выводит статистику"""
    if not distances:
        return {
            "count": 0,
            "min": 0,
            "max": 0,
            "avg": 0,
            "floor_level": 0,
            "object_points": []
        }
    
    floor_level = max(distances)
    min_dist = min(distances)
    max_dist = max(distances)
    avg_dist = sum(distances) / len(distances)
    
    # Точки, которые ближе к лидару (объект)
    threshold = 50  # мм от пола
    object_points = [d for d in distances if d < floor_level - threshold]
    
    return {
        "count": len(distances),
        "min": min_dist,
        "max": max_dist,
        "avg": round(avg_dist, 2),
        "floor_level": floor_level,
        "object_points_count": len(object_points),
        "object_points_min": min(object_points) if object_points else 0,
        "object_points_max": max(object_points) if object_points else 0,
        "object_points_avg": round(sum(object_points) / len(object_points), 2) if object_points else 0,
    }

def save_data(scenario, raw_data, distances, analysis):
    """Сохраняет данные в файл"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"lidar_data_{scenario}_{timestamp}.json"
    
    data = {
        "timestamp": timestamp,
        "scenario": scenario,
        "raw_data": raw_data[:500] + "..." if len(raw_data) > 500 else raw_data,  # Первые 500 символов
        "distances": distances,
        "distances_count": len(distances),
        "analysis": analysis,
        "distances_sample": distances[:30] if distances else []  # Первые 30 точек
    }
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Данные сохранены в {filename}")
    return filename

def print_analysis(analysis, scenario):
    """Выводит анализ в консоль"""
    print("\n" + "="*60)
    print(f"📊 АНАЛИЗ ДАННЫХ: {scenario}")
    print("="*60)
    print(f"Всего точек: {analysis['count']}")
    print(f"Мин. расстояние: {analysis['min']} мм")
    print(f"Макс. расстояние: {analysis['max']} мм")
    print(f"Среднее расстояние: {analysis['avg']} мм")
    print(f"Уровень пола: {analysis['floor_level']} мм")
    print(f"-"*40)
    print(f"Точек объекта (ближе к лидару): {analysis['object_points_count']}")
    if analysis['object_points_count'] > 0:
        print(f"  Мин. объекта: {analysis['object_points_min']} мм")
        print(f"  Макс. объекта: {analysis['object_points_max']} мм")
        print(f"  Среднее объекта: {analysis['object_points_avg']} мм")
    print("="*60)

def interactive_scan():
    """Интерактивный сбор данных"""
    print("\n" + "="*60)
    print("🔬 СКАНИРОВАНИЕ ЛИДАРА - СБОР ДАННЫХ")
    print("="*60)
    print("\nПодготовьте сценарий:")
    print("  1. НЕТ ОБЪЕКТА (пустое поле)")
    print("  2. КОРОБКА ПУСТАЯ")
    print("  3. КОРОБКА ПОЛНАЯ")
    print("\nНажмите Enter для сканирования (или 'q' для выхода)")
    
    data_collection = {}
    
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
            print("❌ Неверный выбор. Введите 1, 2, 3 или q")
            continue
        
        print(f"\n📡 Сканирование: {scenario}...")
        raw_data = get_raw_scan_data()
        
        if raw_data:
            distances = parse_distances(raw_data)
            analysis = analyze_distances(distances)
            print_analysis(analysis, scenario)
            
            filename = save_data(scenario, raw_data, distances, analysis)
            data_collection[scenario] = {
                "filename": filename,
                "analysis": analysis,
                "distances": distances
            }
        else:
            print("❌ Не удалось получить данные")
    
    return data_collection

def compare_data(data_collection):
    """Сравнивает данные между сценариями"""
    if len(data_collection) < 2:
        print("❌ Недостаточно данных для сравнения")
        return
    
    print("\n" + "="*60)
    print("📊 СРАВНЕНИЕ СЦЕНАРИЕВ")
    print("="*60)
    
    for scenario, data in data_collection.items():
        analysis = data["analysis"]
        print(f"\n{scenario}:")
        print(f"  Точки: {analysis['count']}")
        print(f"  Точки объекта: {analysis['object_points_count']}")
        print(f"  Уровень пола: {analysis['floor_level']} мм")
    
    print("\n" + "="*60)
    print("💡 РЕКОМЕНДАЦИИ:")
    
    # Сравниваем количество точек объекта между сценариями
    no_obj = data_collection.get("no_object", {}).get("analysis", {})
    empty = data_collection.get("box_empty", {}).get("analysis", {})
    filled = data_collection.get("box_filled", {}).get("analysis", {})
    
    if no_obj and empty and filled:
        print(f"  Нет объекта: {no_obj.get('object_points_count', 0)} точек")
        print(f"  Коробка пустая: {empty.get('object_points_count', 0)} точек")
        print(f"  Коробка полная: {filled.get('object_points_count', 0)} точек")
        
        # Определяем пороги
        empty_points = empty.get('object_points_count', 0)
        filled_points = filled.get('object_points_count', 0)
        
        threshold_empty = empty_points + 2
        threshold_filled = (empty_points + filled_points) // 2
        
        print(f"\n  Рекомендуемые пороги:")
        print(f"  EMPTY_THRESHOLD = {threshold_empty}  (если <= {threshold_empty} - пусто)")
        print(f"  FILLED_THRESHOLD = {threshold_filled}  (если >= {threshold_filled} - заполнено)")

def main():
    """Основная функция"""
    print("🔬 LIDAR RAW DATA ANALYZER")
    print("Сбор данных для настройки фильтрации\n")
    
    # Собираем данные
    data_collection = interactive_scan()
    
    if data_collection:
        # Сравниваем
        compare_data(data_collection)
        
        print("\n" + "="*60)
        print("📁 Сохраненные файлы:")
        for scenario, data in data_collection.items():
            print(f"  {scenario}: {data['filename']}")
        print("="*60)
        print("\n💡 Используйте эти данные для настройки фильтрации в lidar_client.py")
    
    print("\n✅ Анализ завершен")

if __name__ == "__main__":
    main()