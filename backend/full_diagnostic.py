# backend/full_diagnostic.py

"""
Полная диагностика лидара - проверяем все параметры
"""
import socket
import time
import binascii

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

print("="*80)
print("🔬 ПОЛНАЯ ДИАГНОСТИКА ЛИДАРА")
print("="*80)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5)
sock.connect((LIDAR_HOST, LIDAR_PORT))
print("✅ Подключен")

# 1. АВТОРИЗАЦИЯ
print("\n📡 1. АВТОРИЗАЦИЯ")
print("-"*70)
resp = send_cmd(sock, "sMN SetAccessMode 3 F4724744")
print(f"   Ответ: {resp}")
time.sleep(0.2)

# 2. ПРОВЕРКА УГЛА
print("\n📡 2. ПРОВЕРКА УГЛА")
print("-"*70)
resp = send_cmd(sock, "sRN LMPoutputRange")
print(f"   Ответ: {resp}")

if resp and "LMPoutputRange" in resp:
    parts = resp.split()
    print(f"\n   Парсинг:")
    print(f"   parts: {parts}")

    if len(parts) >= 6:
        resolution_hex = parts[3]
        start_hex = parts[4]
        stop_hex = parts[5]

        resolution_raw = int(resolution_hex, 16)

        try:
            start_raw = int(start_hex, 16)
            if start_raw > 0x7FFFFFFF:
                start_raw = start_raw - 0x100000000
        except:
            start_raw = int(start_hex)

        try:
            stop_raw = int(stop_hex, 16)
            if stop_raw > 0x7FFFFFFF:
                stop_raw = stop_raw - 0x100000000
        except:
            stop_raw = int(stop_hex)

        print(f"\n   Результат:")
        print(f"   Разрешение: {resolution_raw / 10000:.4f}°")
        print(f"   Стартовый: {start_raw / 100:.1f}°")
        print(f"   Конечный: {stop_raw / 100:.1f}°")
        print(f"   Общий: {(stop_raw - start_raw) / 100:.1f}°")

# 3. ПРОВЕРКА СТАТУСА
print("\n📡 3. ПРОВЕРКА СТАТУСА ЛИДАРА")
print("-"*70)
resp = send_cmd(sock, "sRN SCdevicestate")
print(f"   Ответ: {resp}")

# 4. ПОЛУЧЕНИЕ ДАННЫХ
print("\n📡 4. ПОЛУЧЕНИЕ ДАННЫХ")
print("-"*70)
resp = send_cmd(sock, "sRN LMDscandata")
print(f"   Ответ (первые 300 символов):")
print(f"   {resp[:300]}...")

# 5. ПАРСИНГ DIST1
print("\n📡 5. ПАРСИНГ DIST1")
print("-"*70)

all_points = []
if resp and "DIST1" in resp:
    parts = resp.split()

    for i, part in enumerate(parts):
        if part == "DIST1":
            j = i + 1
            skip = 0

            # ПРОПУСКАЕМ 4 СЛУЖЕБНЫХ
            while j < len(parts) and skip < 4:
                print(f"   Служебное #{skip+1}: {parts[j]}")
                j += 1
                skip += 1

            count = 0
            print(f"\n   ТОЧКИ (HEX → DEC):")
            while j < len(parts) and parts[j] not in ["RSSI1", "RSSI2", "DIST2", "DEVICE"]:
                hex_val = parts[j]
                try:
                    value = int(hex_val, 16)
                    if value > 0x7FFFFFFF:
                        value = value - 0x100000000
                    all_points.append(value)
                    count += 1
                    if value > 0:
                        print(f"      [{count:2d}] {hex_val:>8} → {value:>6} мм")
                    else:
                        print(f"      [{count:2d}] {hex_val:>8} → {value:>6} мм ❌ НОЛЬ")
                except:
                    print(f"      [{count+1}] {hex_val} → ОШИБКА")
                j += 1

            print(f"\n   Всего точек: {len(all_points)}")
            break

# 6. АНАЛИЗ
print("\n📡 6. АНАЛИЗ ДАННЫХ")
print("-"*70)

if all_points:
    # Валидные (> 0)
    valid = [d for d in all_points if d > 0]
    print(f"   Валидных (>0): {len(valid)}")

    if valid:
        print(f"   Min: {min(valid)} мм")
        print(f"   Max: {max(valid)} мм")
        print(f"   Avg: {sum(valid)/len(valid):.0f} мм")
        print(f"   Уникальные: {sorted(set(valid))}")

        # Объект (1000-2742 мм)
        object_points = [d for d in valid if 1000 <= d <= 2742]
        if object_points:
            print(f"\n   ✅ ОБЪЕКТ: {len(object_points)} точек")
            print(f"      Значения: {sorted(set(object_points))}")
        else:
            print(f"\n   ❌ ОБЪЕКТ НЕ НАЙДЕН!")

        # Пол (2700-2800 мм)
        floor_points = [d for d in valid if 2700 <= d <= 2800]
        if floor_points:
            print(f"\n   🏗️ ПОЛ: {len(floor_points)} точек")
            print(f"      Значения: {sorted(set(floor_points))}")
        else:
            print(f"\n   ⚠️ ПОЛ НЕ НАЙДЕН!")

        # Шум (0-1000 мм)
        noise_points = [d for d in valid if 0 < d < 1000]
        if noise_points:
            print(f"\n   📢 ШУМ: {len(noise_points)} точек")
            print(f"      Значения: {sorted(set(noise_points))}")
    else:
        print("\n   ❌ НЕТ ВАЛИДНЫХ ТОЧЕК!")
else:
    print("\n   ❌ НЕТ ДАННЫХ!")

# 7. РЕКОМЕНДАЦИИ
print("\n📡 7. РЕКОМЕНДАЦИИ")
print("-"*70)

if not valid:
    print("   ❌ Лидар не видит ничего!")
    print("   Проверьте:")
    print("   - Есть ли питание на лидаре")
    print("   - Правильный ли IP адрес")
    print("   - Не перекрыт ли лазерный луч")
elif len(valid) < 10:
    print("   ⚠️ Лидар видит слишком мало точек!")
    print("   Проверьте:")
    print("   - Расстояние до объекта (должно быть 2-3 м)")
    print("   - Объект должен быть в центре сектора")
    print("   - Нет ли препятствий")
else:
    print("   ✅ Лидар работает нормально")

sock.close()
print("\n🔌 Отключено")