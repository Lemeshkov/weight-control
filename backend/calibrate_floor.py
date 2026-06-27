# backend/calibrate_floor.py
"""
Скрипт для калибровки уровня пола
Измеряет расстояние до пола и сохраняет в файл конфигурации
"""
import socket
import time
import json
import os
from datetime import datetime
from collections import Counter

# ═══════════════════════════════════════════════════════════
# НАСТРОЙКИ
# ═══════════════════════════════════════════════════════════
LIDAR_HOST = "192.168.1.101"
LIDAR_PORT = 2111
CONFIG_FILE = "floor_config.json"  # Файл для сохранения калибровки


def connect_lidar(host=LIDAR_HOST, port=LIDAR_PORT):
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
    """Парсинг расстояний из DIST1"""
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
                        if 100 < value < 5000:
                            distances.append(value)
                except ValueError:
                    pass
                j += 1
            break
    
    return distances


def find_floor_level(distances):
    """
    Находит уровень пола по данным сканирования
    Использует несколько методов для надежности
    """
    if not distances:
        return 0
    
    # ═══════════════════════════════════════════════════════════
    # МЕТОД 1: Самое частое значение в диапазоне 1500-3500 мм
    # ═══════════════════════════════════════════════════════════
    floor_candidates = [d for d in distances if 1500 <= d <= 3500]
    if floor_candidates:
        counter = Counter(floor_candidates)
        floor_level = counter.most_common(1)[0][0]
        return floor_level
    
    # ═══════════════════════════════════════════════════════════
    # МЕТОД 2: Максимальное значение (если нет точек в диапазоне)
    # ═══════════════════════════════════════════════════════════
    return max(distances)


def calibrate_floor(measurements=5):
    """
    Калибровка уровня пола
    Делает несколько измерений и усредняет результат
    """
    print("\n" + "="*60)
    print("🔬 КАЛИБРОВКА УРОВНЯ ПОЛА")
    print("="*60)
    print("\nУбедитесь, что:")
    print("  1. Лидар включен и подключен")
    print("  2. Под лидаром НЕТ объектов (пустое поле)")
    print("  3. Лидар смотрит на пол")
    print("\nНажмите Enter для начала...")
    input()
    
    sock = connect_lidar()
    if not sock:
        return False
    
    try:
        floor_levels = []
        
        for i in range(measurements):
            print(f"\n📡 Измерение {i+1}/{measurements}...")
            
            raw_data = get_scan_data(sock)
            if not raw_data:
                print("  ❌ Ошибка получения данных")
                continue
            
            distances = parse_distances(raw_data)
            if not distances:
                print("  ❌ Нет данных")
                continue
            
            floor_level = find_floor_level(distances)
            floor_levels.append(floor_level)
            
            print(f"  📏 Уровень пола: {floor_level} мм")
            
            # Пауза между измерениями
            if i < measurements - 1:
                time.sleep(0.5)
        
        if not floor_levels:
            print("\n❌ Не удалось получить ни одного измерения")
            return False
        
        # Усредняем результат
        avg_floor = int(sum(floor_levels) / len(floor_levels))
        min_floor = min(floor_levels)
        max_floor = max(floor_levels)
        
        print("\n" + "="*60)
        print("📊 РЕЗУЛЬТАТЫ КАЛИБРОВКИ")
        print("="*60)
        print(f"  Измерений: {len(floor_levels)}")
        print(f"  Минимум: {min_floor} мм")
        print(f"  Максимум: {max_floor} мм")
        print(f"  Среднее: {avg_floor} мм")
        print(f"  Разброс: {max_floor - min_floor} мм")
        
        # Проверяем стабильность
        if max_floor - min_floor > 100:
            print("\n⚠️ ВНИМАНИЕ: Большой разброс измерений!")
            print("   Рекомендуется повторить калибровку")
            print("   Проверьте, что под лидаром нет объектов")
        
        # Сохраняем результат
        config = {
            "floor_level_mm": avg_floor,
            "measurements": floor_levels,
            "timestamp": datetime.now().isoformat(),
            "min_mm": min_floor,
            "max_mm": max_floor,
            "stable": max_floor - min_floor <= 100
        }
        
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Результат сохранен в {CONFIG_FILE}")
        print(f"   Уровень пола: {avg_floor} мм")
        
        return True
        
    finally:
        sock.close()
        print("\n🔌 Отключено")


def load_floor_config():
    """Загружает сохраненную калибровку"""
    if not os.path.exists(CONFIG_FILE):
        return None
    
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config
    except Exception as e:
        print(f"❌ Ошибка загрузки: {e}")
        return None


def show_status():
    """Показывает текущую калибровку"""
    config = load_floor_config()
    if not config:
        print("\n❌ Калибровка не найдена. Запустите калибровку.")
        return
    
    print("\n" + "="*60)
    print("📊 ТЕКУЩАЯ КАЛИБРОВКА")
    print("="*60)
    print(f"  Уровень пола: {config.get('floor_level_mm', '?')} мм")
    print(f"  Дата: {config.get('timestamp', '?')}")
    print(f"  Измерений: {len(config.get('measurements', []))}")
    print(f"  Стабильность: {'✅ Стабильно' if config.get('stable', False) else '⚠️ Нестабильно'}")


def main():
    """Главное меню"""
    print("\n🔬 КАЛИБРОВКА УРОВНЯ ПОЛА")
    print("="*60)
    print("  1 - Провести калибровку")
    print("  2 - Показать текущую калибровку")
    print("  3 - Использовать автоматическое определение (default)")
    print("  0 - Выход")
    
    choice = input("\nВыберите: ").strip()
    
    if choice == "1":
        calibrate_floor(measurements=5)
    elif choice == "2":
        show_status()
    elif choice == "3":
        # Удаляем файл калибровки, чтобы использовать автоматическое определение
        if os.path.exists(CONFIG_FILE):
            os.remove(CONFIG_FILE)
            print("\n✅ Калибровка удалена. Используется автоматическое определение.")
        else:
            print("\nℹ️ Калибровка уже удалена.")
    elif choice == "0":
        print("\nДо свидания!")
    else:
        print("\n❌ Неверный выбор")


if __name__ == "__main__":
    main()