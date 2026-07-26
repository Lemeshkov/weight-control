# backend/check_scan_area_fixed.py

"""
Проверяет, где находится центр сканирования и что видит лидар
"""
import socket
import time

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

def parse_angle_value(val_str):
    """Парсит значение угла - может быть HEX или десятичным"""
    val_str = val_str.strip()

    # Проверяем, является ли HEX (содержит буквы A-F или только цифры в HEX формате)
    try:
        # Пробуем как HEX
        val = int(val_str, 16)
        if val > 0x7FFFFFFF:
            val = val - 0x100000000
        return val
    except ValueError:
        pass

    # Пробуем как десятичное
    try:
        return int(val_str)
    except ValueError:
        return 0

print("="*80)
print("🔍 ПРОВЕРКА ЗОНЫ СКАНИРОВАНИЯ")
print("="*80)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5)
sock.connect((LIDAR_HOST, LIDAR_PORT))
print("✅ Подключен")

# 1. Авторизация
print("\n📡 1. Авторизация...")
resp = send_cmd(sock, "sMN SetAccessMode 3 F4724744")
print(f"   Ответ: {resp}")
time.sleep(0.2)

# 2. Проверка угла
print("\n📡 2. Проверка угла...")
resp = send_cmd(sock, "sRN LMPoutputRange")
print(f"   Ответ: {resp}")

if resp and "LMPoutputRange" in resp:
    parts = resp.split()
    print(f"   parts: {parts}")

    if len(parts) >= 6:
        resolution_raw = int(parts[3], 16)
        start_raw = parse_angle_value(parts[4])
        stop_raw = parse_angle_value(parts[5])

        print(f"\n📊 ТЕКУЩИЙ УГОЛ:")
        print(f"   Разрешение: {resolution_raw / 10000:.4f}°")
        print(f"   Стартовый: {start_raw / 100:.1f}°")
        print(f"   Конечный: {stop_raw / 100:.1f}°")
        print(f"   Общий: {(stop_raw - start_raw) / 100:.1f}°")

# 3. Получение данных с детальным анализом
print("\n📡 3. Получение данных...")
resp = send_cmd(sock, "sRN LMDscandata")

if resp and "DIST1" in resp:
    parts = resp.split()
    for i, part in enumerate(parts):
        if part == "DIST1":
            j = i + 1
            skip = 0
            print(f"\n   Служебные значения:")
            while j < len(parts) and skip < 4:
                print(f"      {parts[j]}")
                j += 1
                skip += 1

            print(f"\n   📊 ТОЧКИ СКАНИРОВАНИЯ:")
            points = []
            count = 0
            while j < len(parts) and parts[j] not in ["RSSI1", "RSSI2", "DIST2", "DEVICE"]:
                try:
                    value = int(parts[j], 16)
                    if value > 0x7FFFFFFF:
                        value = value - 0x100000000
                    points.append(value)
                    count += 1
                    if value > 0:
                        print(f"      [{count:2d}] {parts[j]:>8} → {value:>6} мм ✅")
                    else:
                        print(f"      [{count:2d}] {parts[j]:>8} → {value:>6} мм ❌")
                except:
                    print(f"      [{count+1}] {parts[j]} → ОШИБКА")
                j += 1
            break

# 4. Анализ
print("\n📡 4. АНАЛИЗ:")
print("-"*70)

if points:
    valid = [d for d in points if d > 0]
    print(f"   Всего точек: {len(points)}")
    print(f"   Валидных (>0): {len(valid)}")

    if valid:
        print(f"   Минимальное расстояние: {min(valid)} мм")
        print(f"   Максимальное расстояние: {max(valid)} мм")
        print(f"   Среднее: {sum(valid)/len(valid):.0f} мм")

        # Проверяем, есть ли объект на 2-3 метрах
        far_points = [d for d in valid if 2000 <= d <= 3000]
        if far_points:
            print(f"\n   ✅ ОБЪЕКТ НА 2-3 МЕТРАХ: {len(far_points)} точек")
            print(f"      Значения: {sorted(far_points)}")
        else:
            print(f"\n   ❌ ОБЪЕКТ НА 2-3 МЕТРАХ НЕ НАЙДЕН!")
            print(f"      Ближайшие точки: {sorted(valid)[:10]}")

            # Подсказка
            if valid and min(valid) < 1500:
                print(f"\n   ⚠️ Лидар видит объект на {min(valid)} мм (1.3 м)")
                print(f"   Это НЕ коробка на 2.5 метрах!")
                print(f"\n   Возможные причины:")
                print(f"   1. Лидар смотрит не на коробку, а на что-то другое")
                print(f"   2. Коробка не в центре сектора сканирования")
                print(f"   3. Сбились настройки нулевой точки")
else:
    print("   ❌ НЕТ ДАННЫХ!")

sock.close()
print("\n🔌 Отключено")