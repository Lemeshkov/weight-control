# backend/diagnostic_scan.py  данные которые видит лидар 

"""
Полная диагностика - проверяем все параметры лидара
"""
import socket
import time
import math

LIDAR_HOST = "192.168.1.101"
LIDAR_PORT = 2111

def send_cmd(sock, cmd, wait=0.3):
    full_cmd = f"\x02{cmd}\x03"
    sock.send(full_cmd.encode('utf-8'))
    time.sleep(wait)
    response = sock.recv(65535)
    decoded = response.decode('utf-8', errors='ignore')
    decoded = decoded.strip('\x02\x03')
    return decoded

def get_scan_data(sock):
    """Получить данные сканирования с дополнительной информацией"""
    resp = send_cmd(sock, "sRN LMDscandata")
    return resp

def parse_scan_info(raw_data):
    """Парсит информацию о сканировании"""
    if not raw_data:
        return None

    parts = raw_data.split()

    # Ищем информацию о сканировании
    info = {
        "raw": raw_data[:200],
        "parts_count": len(parts),
        "has_DIST1": "DIST1" in parts,
        "has_RSSI1": "RSSI1" in parts,
        "distances": []
    }

    # Парсим расстояния
    for i, part in enumerate(parts):
        if part == "DIST1" and i + 1 < len(parts):
            j = i + 1
            skip_count = 0
            while j < len(parts) and skip_count < 4:
                j += 1
                skip_count += 1

            count = 0
            while j < len(parts) and parts[j] not in ["RSSI1", "RSSI2", "DIST2", "DEVICE"]:
                try:
                    hex_val = parts[j].strip()
                    if hex_val:
                        value = int(hex_val, 16)
                        if value > 0x7FFFFFFF:
                            value = value - 0x100000000
                        info["distances"].append(value)
                        count += 1
                except ValueError:
                    pass
                j += 1
            break

    return info

def get_angle_info(sock):
    """Получить информацию об угле"""
    resp = send_cmd(sock, "sRN LMPoutputRange")
    if resp and "LMPoutputRange" in resp:
        parts = resp.split()
        if len(parts) >= 6:
            try:
                resolution_raw = int(parts[3], 16)
                start_raw = int(parts[4], 16) if 'FFFF' in parts[4] else int(parts[4])
                stop_raw = int(parts[5], 16) if 'FFFF' in parts[5] else int(parts[5])

                if start_raw > 0x7FFFFFFF:
                    start_raw = start_raw - 0x100000000
                if stop_raw > 0x7FFFFFFF:
                    stop_raw = stop_raw - 0x100000000

                return {
                    "resolution": resolution_raw / 10000,
                    "start": start_raw / 100,
                    "stop": stop_raw / 100,
                    "total": (stop_raw - start_raw) / 100,
                    "start_hex": parts[4],
                    "stop_hex": parts[5]
                }
            except:
                pass
    return None

print("="*70)
print("🔍 ДИАГНОСТИКА ЛИДАРА")
print("="*70)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5)
sock.connect((LIDAR_HOST, LIDAR_PORT))
print("✅ Подключен")

# 1. Проверка угла
print("\n" + "-"*70)
print("1️⃣ УГОЛ СКАНИРОВАНИЯ")
print("-"*70)

angle = get_angle_info(sock)
if angle:
    print(f"   Разрешение: {angle['resolution']:.4f}°")
    print(f"   Стартовый: {angle['start']:.1f}°")
    print(f"   Конечный: {angle['stop']:.1f}°")
    print(f"   Общий: {angle['total']:.1f}°")
    print(f"   HEX: start={angle['start_hex']}, stop={angle['stop_hex']}")

# 2. Получение данных сканирования
print("\n" + "-"*70)
print("2️⃣ ДАННЫЕ СКАНИРОВАНИЯ")
print("-"*70)

scan_data = get_scan_data(sock)
info = parse_scan_info(scan_data)

if info:
    print(f"   Raw (первые 200 символов):")
    print(f"   {info['raw']}")
    print(f"\n   Всего частей: {info['parts_count']}")
    print(f"   Есть DIST1: {info['has_DIST1']}")
    print(f"   Есть RSSI1: {info['has_RSSI1']}")

    distances = info['distances']
    print(f"\n   Расстояний: {len(distances)}")

    if distances:
        # Фильтруем нулевые значения
        valid = [d for d in distances if d > 10]
        print(f"   Валидных (>10 мм): {len(valid)}")

        if valid:
            print(f"   Min: {min(valid)} мм")
            print(f"   Max: {max(valid)} мм")
            print(f"   Avg: {sum(valid)/len(valid):.0f} мм")

            # Группировка
            bins = {}
            for d in valid:
                bin_key = int(d / 50) * 50
                bins[bin_key] = bins.get(bin_key, 0) + 1

            print(f"\n   Топ-5 бинов:")
            sorted_bins = sorted(bins.items(), key=lambda x: x[1], reverse=True)
            for i, (bin_val, count) in enumerate(sorted_bins[:5]):
                print(f"      #{i+1}: {bin_val} мм -> {count} точек")

            # Поиск объекта
            FLOOR = 2792
            object_points = [d for d in valid if d < 2700]
            if object_points:
                min_obj = min(object_points)
                height = FLOOR - min_obj
                print(f"\n   📦 ОБЪЕКТ НАЙДЕН:")
                print(f"      Точек: {len(object_points)}")
                print(f"      Min: {min_obj} мм")
                print(f"      Высота: {height} мм ({height/10:.1f} см)")
                print(f"      Реальное расстояние: {min_obj + 1000} мм")
                print(f"      Реальная высота: {FLOOR - (min_obj + 1000)} мм")
            else:
                print(f"\n   ❌ ОБЪЕКТ НЕ НАЙДЕН (нет точек < 2700 мм)")
        else:
            print("   ❌ Нет валидных расстояний!")
    else:
        print("   ❌ Нет расстояний!")

# 3. Рекомендации
print("\n" + "-"*70)
print("3️⃣ РЕКОМЕНДАЦИИ")
print("-"*70)

if info and info['distances']:
    valid = [d for d in info['distances'] if d > 10]

    if len(valid) < 10:
        print("\n   ⚠️ МАЛО ТОЧЕК! Лидар видит только", len(valid), "точек")
        print("\n   Возможные причины:")
        print("   1. Коробка стоит слишком далеко (> 30 м)")
        print("   2. Коробка стоит слишком близко (< 1 м)")
        print("   3. Коробка не попадает в сектор сканирования")
        print("   4. Лидар не настроен (нужна калибровка)")

        print("\n   📌 ПРОВЕРЬТЕ:")
        print("   - Расстояние от лидара до коробки (должно быть 2-5 м)")
        print("   - Коробка должна быть прямо перед лидаром")
        print("   - Угол сканирования: 50° (-25°…+25°)")
        print("   - Нет препятствий между лидаром и коробкой")

        print("\n   📏 ИДЕАЛЬНОЕ РАССТОЯНИЕ:")
        print("   - Коробка M: 2.0 - 2.5 м от лидара")
        print("   - Коробка L: 2.5 - 3.0 м от лидара")
        print("   - Грузовик: 3.0 - 5.0 м от лидара")
    else:
        print("\n   ✅ Достаточно точек для работы")

sock.close()
print("\n🔌 Отключено")