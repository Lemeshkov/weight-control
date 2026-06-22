# backend/diagnose_lidar_raw.py
"""
Диагностика сырых данных с лидара
Показывает реальные данные и помогает настроить фильтрацию
"""
import socket
import time
import json
from datetime import datetime
from collections import Counter
import math

def connect_lidar(host="192.168.1.101", port=2111):
    """Подключение к лидару"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        print(f"✅ Подключен к {host}:{port}")
        
        # Авторизация
        sock.send(b"\x02sMN SetAccessMode 3 F4724744\x03")
        time.sleep(0.2)
        sock.send(b"\x02sMN Run\x03")
        time.sleep(0.2)
        
        return sock
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None

def get_raw_data(sock):
    """Получение сырых данных"""
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

def parse_all_distances(raw_data):
    """Парсинг ВСЕХ расстояний из DIST1"""
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
                        # Не фильтруем - берем все значения
                        distances.append(value)
                except ValueError:
                    pass
                j += 1
            break
    
    return distances

def analyze_distances(distances, name="Данные"):
    """Детальный анализ расстояний"""
    if not distances:
        print("❌ Нет данных")
        return
    
    print(f"\n{'='*70}")
    print(f"📊 АНАЛИЗ {name}")
    print(f"{'='*70}")
    
    # Базовая статистика
    total = len(distances)
    print(f"\n📌 ОБЩАЯ СТАТИСТИКА:")
    print(f"  Всего точек: {total}")
    print(f"  Мин: {min(distances)} мм")
    print(f"  Макс: {max(distances)} мм")
    print(f"  Среднее: {sum(distances)/total:.1f} мм")
    
    # Анализ уникальных значений
    counter = Counter(distances)
    most_common = counter.most_common(10)
    
    print(f"\n📌 10 САМЫХ ЧАСТЫХ ЗНАЧЕНИЙ:")
    for val, count in most_common:
        print(f"  {val} мм: {count} раз ({count/total*100:.1f}%)")
    
    # Анализ по диапазонам
    ranges = [
        (0, 100, "0-100 мм (шум/мусор)"),
        (100, 500, "100-500 мм (очень близко)"),
        (500, 1000, "500-1000 мм (близко)"),
        (1000, 2000, "1000-2000 мм (средне)"),
        (2000, 3000, "2000-3000 мм (далеко)"),
        (3000, 5000, "3000-5000 мм (очень далеко)"),
        (5000, 10000, "5000+ мм (мусор)"),
    ]
    
    print(f"\n📌 РАСПРЕДЕЛЕНИЕ ПО ДИАПАЗОНАМ:")
    for min_val, max_val, desc in ranges:
        count = sum(1 for d in distances if min_val <= d <= max_val)
        if count > 0:
            print(f"  {desc}: {count} точек ({count/total*100:.1f}%)")
    
    # Анализ мусорных значений
    garbage = [d for d in distances if d == 0 or d > 5000]
    if garbage:
        print(f"\n⚠️ МУСОРНЫЕ ЗНАЧЕНИЯ (0 или >5000): {len(garbage)} точек ({len(garbage)/total*100:.1f}%)")
    
    # Определение уровня пола
    # Пол - это самое частое значение в диапазоне 1500-3000 мм
    floor_candidates = [d for d in distances if 1500 <= d <= 3000]
    if floor_candidates:
        floor_counter = Counter(floor_candidates)
        floor_level = floor_counter.most_common(1)[0][0]
        floor_count = floor_counter.most_common(1)[0][1]
        print(f"\n🏗️ УРОВЕНЬ ПОЛА:")
        print(f"  Наиболее частое значение: {floor_level} мм ({floor_count} раз)")
    else:
        print(f"\n⚠️ НЕ НАЙДЕН УРОВЕНЬ ПОЛА в диапазоне 1500-3000 мм")
        if distances:
            print(f"  Максимальное значение: {max(distances)} мм")
    
    # Точки объекта (ближе к лидару)
    if floor_level:
        object_threshold = 100  # мм от пола
        object_points = [d for d in distances if d < floor_level - object_threshold]
        
        print(f"\n📦 ТОЧКИ ОБЪЕКТА (ближе {object_threshold}мм от пола):")
        print(f"  Количество: {len(object_points)}")
        if object_points:
            print(f"  Мин: {min(object_points)} мм")
            print(f"  Макс: {max(object_points)} мм")
            print(f"  Среднее: {sum(object_points)/len(object_points):.1f} мм")
            
            # Анализ распределения точек объекта
            obj_counter = Counter(object_points)
            obj_common = obj_counter.most_common(5)
            print(f"  Частые значения: {obj_common}")
    
    return {
        "total": total,
        "floor_level": floor_level if 'floor_level' in locals() else None,
        "object_points_count": len(object_points) if 'object_points' in locals() else 0
    }

def diagnose_lidar():
    """Основная диагностика"""
    print("\n" + "="*70)
    print("🔬 ДИАГНОСТИКА СЫРЫХ ДАННЫХ ЛИДАРА")
    print("="*70)
    
    # Подключаемся
    sock = connect_lidar()
    if not sock:
        return
    
    try:
        # Получаем данные несколько раз для стабильности
        print("\n📡 Получение данных...")
        raw = get_raw_data(sock)
        if not raw:
            print("❌ Не удалось получить данные")
            return
        
        # Парсим все расстояния
        distances = parse_all_distances(raw)
        
        if not distances:
            print("❌ Не удалось распарсить DIST1")
            # Показываем сырые данные для отладки
            print("\n📄 СЫРЫЕ ДАННЫЕ (первые 500 символов):")
            print(raw[:500])
            return
        
        # Анализируем
        analysis = analyze_distances(distances, "ТЕКУЩЕЕ СКАНИРОВАНИЕ")
        
        # Сохраняем в файл
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"lidar_diagnostic_{timestamp}.json"
        
        data = {
            "timestamp": timestamp,
            "total_points": len(distances),
            "distances": distances,
            "distances_sample": distances[:50],
            "analysis": {
                "min": min(distances),
                "max": max(distances),
                "avg": sum(distances)/len(distances),
                "floor_level": analysis.get("floor_level"),
                "object_points_count": analysis.get("object_points_count", 0)
            }
        }
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Данные сохранены в {filename}")
        
        # ═══════════════════════════════════════════════════════════
        # РЕКОМЕНДАЦИИ ПО НАСТРОЙКЕ
        # ═══════════════════════════════════════════════════════════
        print("\n" + "="*70)
        print("💡 РЕКОМЕНДАЦИИ ПО НАСТРОЙКЕ")
        print("="*70)
        
        # 1. Анализ мусора
        garbage = [d for d in distances if d == 0 or d > 5000]
        if garbage:
            print(f"\n⚠️ Найдено {len(garbage)} мусорных значений (0 или >5000)")
            print(f"   Рекомендуется фильтровать значения > 5000 мм")
        
        # 2. Анализ уровня пола
        floor = analysis.get("floor_level")
        if floor:
            print(f"\n🏗️ Уровень пола: {floor} мм")
            print(f"   Рекомендуется FLOOR_THRESHOLD = 100-150 мм")
        
        # 3. Анализ точек объекта
        obj_count = analysis.get("object_points_count", 0)
        print(f"\n📦 Точек объекта: {obj_count}")
        
        if obj_count < 10:
            print(f"   ⚠️ ОЧЕНЬ МАЛО ТОЧЕК! Возможно объект отсутствует или неправильная фильтрация")
            print(f"   Рекомендуется проверить:")
            print(f"   - Есть ли объект под лидаром?")
            print(f"   - Правильно ли работает фильтрация угла?")
            print(f"   - Не слишком ли высокий порог отсечения пола?")
        elif obj_count < 30:
            print(f"   📦 Мало точек - возможно пустая коробка")
            print(f"   Рекомендуется EMPTY_POINTS_THRESHOLD = {obj_count + 2}")
        else:
            print(f"   📦 Много точек - возможно заполненная коробка")
            print(f"   Рекомендуется FILLED_POINTS_THRESHOLD = {obj_count - 5}")
        
        print("\n" + "="*70)
        print("📋 ДЛЯ НАСТРОЙКИ В lidar_client.py:")
        print(f"  self.FLOOR_THRESHOLD = 100  # мм - отсечение пола")
        print(f"  self.MIN_VALID_DISTANCE = 100  # мм - минимальное расстояние")
        print(f"  self.MAX_VALID_DISTANCE = 3000  # мм - максимальное расстояние")
        print("="*70)
        
    finally:
        sock.close()
        print("\n🔌 Отключено")

def interactive_test():
    """Интерактивный тест - несколько сканирований"""
    print("\n" + "="*70)
    print("🔄 ИНТЕРАКТИВНЫЙ ТЕСТ (нажмите Enter для сканирования, q для выхода)")
    print("="*70)
    
    sock = connect_lidar()
    if not sock:
        return
    
    scan_count = 0
    all_analyses = []
    
    try:
        while True:
            cmd = input("\nНажмите Enter для сканирования (или 'q'): ").strip()
            if cmd == 'q':
                break
            
            print(f"\n📡 Сканирование #{scan_count + 1}...")
            raw = get_raw_data(sock)
            if not raw:
                print("❌ Ошибка получения данных")
                continue
            
            distances = parse_all_distances(raw)
            if not distances:
                print("❌ Ошибка парсинга")
                continue
            
            scan_count += 1
            analysis = analyze_distances(distances, f"СКАН #{scan_count}")
            all_analyses.append({
                "scan": scan_count,
                "total": len(distances),
                "object_count": analysis.get("object_points_count", 0),
                "floor": analysis.get("floor_level")
            })
            
            # Показываем стабильность
            if scan_count > 1:
                print(f"\n📊 СТАБИЛЬНОСТЬ ДАННЫХ:")
                for a in all_analyses:
                    print(f"  Скан #{a['scan']}: {a['object_count']} точек объекта")
                
                # Проверяем разброс
                obj_counts = [a['object_count'] for a in all_analyses]
                if max(obj_counts) - min(obj_counts) > 10:
                    print(f"\n⚠️ ВНИМАНИЕ: Большой разброс точек объекта!")
                    print(f"   Мин: {min(obj_counts)}, Макс: {max(obj_counts)}")
                    print(f"   Рекомендуется проверить стабильность данных")
    
    finally:
        sock.close()
        print("\n🔌 Отключено")
        print(f"\n✅ Выполнено сканирований: {scan_count}")

if __name__ == "__main__":
    print("\n🔬 ДИАГНОСТИКА ЛИДАРА")
    print("1 - Быстрая диагностика")
    print("2 - Интерактивный тест (несколько сканирований)")
    
    choice = input("\nВыберите (1/2): ").strip()
    
    if choice == '1':
        diagnose_lidar()
    elif choice == '2':
        interactive_test()
    else:
        diagnose_lidar()