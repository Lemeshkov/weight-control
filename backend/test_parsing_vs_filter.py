# backend/test_parsing_vs_filter.py
"""
Сравнение сырых данных и отфильтрованных
"""
import socket
import time

LIDAR_HOST = "192.168.1.101"
LIDAR_PORT = 2111


def send_cmd(sock, cmd, wait=0.3):
    full_cmd = f"\x02{cmd}\x03"
    sock.send(full_cmd.encode('utf-8'))
    time.sleep(wait)
    try:
        response = sock.recv(65535)
        return response.decode('utf-8', errors='ignore').strip('\x02\x03')
    except:
        return "TIMEOUT"


def parse_distances_correct(raw_data):
    """Правильный парсинг с пропуском 4 служебных полей"""
    if not raw_data:
        return []

    parts = raw_data.split()
    distances = []

    for i, part in enumerate(parts):
        if part == "DIST1":
            j = i + 1
            # Пропускаем 4 служебных поля
            j += 4

            while j < len(parts) and parts[j] not in ["RSSI1", "RSSI2", "DIST2", "DEVICE"]:
                try:
                    hex_val = parts[j].strip()
                    if hex_val:
                        value = int(hex_val, 16)
                        if value > 0x7FFFFFFF:
                            value = value - 0x100000000
                        if 0 < value < 50000:
                            distances.append(value)
                except:
                    pass
                j += 1
            break

    return distances


print("=" * 80)
print("🔍 СРАВНЕНИЕ: СЫРЫЕ vs ОТФИЛЬТРОВАННЫЕ")
print("=" * 80)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5)
sock.connect((LIDAR_HOST, LIDAR_PORT))
print("✅ Подключен")

send_cmd(sock, "sMN Logout")
time.sleep(0.2)
send_cmd(sock, "sMN SetAccessMode 3 F4724744")
time.sleep(0.3)
send_cmd(sock, "sMN Run")
time.sleep(0.3)

raw_response = send_cmd(sock, "sRN LMDscandata", wait=1)

# 1. Сырые данные (без фильтрации)
raw_distances = parse_distances_correct(raw_response)

print(f"\n📊 СЫРЫЕ ДАННЫЕ (без фильтрации):")
print(f"   Всего точек: {len(raw_distances)}")
if raw_distances:
    print(f"   Минимальное: {min(raw_distances)} мм")
    print(f"   Максимальное: {max(raw_distances)} мм")

    # Проверяем наличие пола
    floor = [d for d in raw_distances if 2700 <= d <= 2800]
    box = [d for d in raw_distances if 2200 <= d <= 2600]
    walls = [d for d in raw_distances if d < 500]

    print(f"\n   📦 Коробка (2200-2600): {len(box)} точек")
    print(f"   🏗️ Пол (2700-2800): {len(floor)} точек")
    print(f"   🧱 Стены ниши (<500): {len(walls)} точек")

# 2. Применяем фильтр из вашего кода
MIN_VALID = 100
MAX_VALID = 3000

filtered = [d for d in raw_distances if MIN_VALID <= d <= MAX_VALID]

print(f"\n📊 ПОСЛЕ ФИЛЬТРАЦИИ (100-3000 мм):")
print(f"   Всего точек: {len(filtered)}")
if filtered:
    print(f"   Минимальное: {min(filtered)} мм")
    print(f"   Максимальное: {max(filtered)} мм")

    floor = [d for d in filtered if 2700 <= d <= 2800]
    box = [d for d in filtered if 2200 <= d <= 2600]

    print(f"\n   📦 Коробка (2200-2600): {len(box)} точек")
    print(f"   🏗️ Пол (2700-2800): {len(floor)} точек")

# 3. Если пол есть в сырых, но нет в отфильтрованных
if raw_distances and filtered:
    raw_has_floor = any(2700 <= d <= 2800 for d in raw_distances)
    filtered_has_floor = any(2700 <= d <= 2800 for d in filtered)

    if raw_has_floor and not filtered_has_floor:
        print("\n" + "=" * 80)
        print("⚠️ ПРОБЛЕМА В ФИЛЬТРАЦИИ!")
        print("=" * 80)
        print("   В сырых данных есть пол, но фильтр его отсекает!")
        print("   Проверьте MIN_VALID_DISTANCE и MAX_VALID_DISTANCE")
    elif raw_has_floor and filtered_has_floor:
        print("\n" + "=" * 80)
        print("✅ ВСЕ РАБОТАЕТ!")
        print("=" * 80)
        print("   И в сырых, и в отфильтрованных данных есть пол")
    else:
        print("\n" + "=" * 80)
        print("⚠️ ПРОБЛЕМА В ПАРСИНГЕ!")
        print("=" * 80)
        print("   В сырых данных нет пола, хотя в SOPAS ET он виден")
        print("   Проверьте парсинг DIST1")

sock.close()
print("\n🔌 Отключено")