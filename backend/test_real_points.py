# backend/test_real_points.py
"""
Тест: сколько реальных точек от коробки
"""
import socket
import time

LIDAR_HOST = "192.168.1.101"
LIDAR_PORT = 2111

# РЕАЛЬНЫЕ ПАРАМЕТРЫ
FLOOR_LEVEL = 2742           # мм - уровень пола
BOX_HEIGHT_MIN = 200         # мм - минимальная высота коробки
BOX_HEIGHT_MAX = 500         # мм - максимальная высота коробки

# Расстояние до коробки = пол - высота коробки
BOX_DIST_MIN = FLOOR_LEVEL - BOX_HEIGHT_MAX   # 2742 - 500 = 2242 мм
BOX_DIST_MAX = FLOOR_LEVEL - BOX_HEIGHT_MIN   # 2742 - 200 = 2542 мм

WALL_THRESHOLD = 500         # мм - стены ниши (исключаем)


def send_cmd(sock, cmd, wait=0.3):
    full_cmd = f"\x02{cmd}\x03"
    sock.send(full_cmd.encode('utf-8'))
    time.sleep(wait)
    response = sock.recv(65535)
    return response.decode('utf-8', errors='ignore').strip('\x02\x03')


def parse_distances(raw_data):
    """Парсит все расстояния из сырых данных"""
    if not raw_data:
        return []

    parts = raw_data.split()
    distances = []

    for i, part in enumerate(parts):
        if part == "DIST1" and i + 1 < len(parts):
            j = i + 1
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
                        distances.append(value)
                except ValueError:
                    pass
                j += 1
            break

    return distances


def get_angle_info(sock):
    resp = send_cmd(sock, "sRN LMPoutputRange")
    if resp and "LMPoutputRange" in resp:
        parts = resp.split()
        if len(parts) >= 6:
            try:
                start_raw = int(parts[4], 16)
                stop_raw = int(parts[5], 16)
                if start_raw > 0x7FFFFFFF:
                    start_raw = start_raw - 0x100000000
                if stop_raw > 0x7FFFFFFF:
                    stop_raw = stop_raw - 0x100000000
                return {
                    "start": start_raw / 100,
                    "stop": stop_raw / 100,
                    "total": (stop_raw - start_raw) / 100
                }
            except:
                pass
    return None


print("=" * 80)
print("📊 ТЕСТ: РЕАЛЬНЫЕ ТОЧКИ ОТ КОРОБКИ")
print("=" * 80)
print(f"\n📐 ПАРАМЕТРЫ:")
print(f"   Уровень пола: {FLOOR_LEVEL} мм")
print(f"   Высота коробки: {BOX_HEIGHT_MIN}-{BOX_HEIGHT_MAX} мм")
print(f"   Расстояние до коробки: {BOX_DIST_MIN}-{BOX_DIST_MAX} мм")
print(f"   Стены ниши: < {WALL_THRESHOLD} мм")

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5)
sock.connect((LIDAR_HOST, LIDAR_PORT))
print("\n✅ Подключен")

# 1. Авторизация
print("\n📡 Авторизация...")
send_cmd(sock, "sMN Logout")
time.sleep(0.2)
send_cmd(sock, "sMN SetAccessMode 3 F4724744")
time.sleep(0.2)
send_cmd(sock, "sMN Run")
time.sleep(0.2)

# 2. Получаем угол
print("\n📡 Получение угла...")
angle = get_angle_info(sock)
if angle:
    print(f"   Угол: {angle['start']:.1f}° ... {angle['stop']:.1f}° (всего {angle['total']:.1f}°)")
else:
    print("   ❌ Не удалось получить угол")

# 3. Получаем данные
print("\n📡 Получение данных...")
raw_data = send_cmd(sock, "sRN LMDscandata", wait=1)
distances = parse_distances(raw_data)

print(f"\n📊 СЫРЫЕ ДАННЫЕ:")
print(f"   Всего точек: {len(distances)}")

if not distances:
    print("   ❌ Нет данных!")
    sock.close()
    exit()

# 4. Анализ по категориям
print("\n" + "-" * 80)
print("📊 КАТЕГОРИИ ТОЧЕК:")
print("-" * 80)

# Категория 1: Стены ниши (ближе 500 мм)
walls = [d for d in distances if d < WALL_THRESHOLD]
print(f"\n1️⃣ СТЕНЫ НИШИ (< {WALL_THRESHOLD} мм):")
print(f"   Точек: {len(walls)}")
if walls:
    print(f"   Диапазон: {min(walls)} - {max(walls)} мм")
    print(f"   Среднее: {sum(walls) / len(walls):.0f} мм")

# Категория 2: Коробка (2242-2542 мм - реальное расстояние до коробки на полу)
box_points = [d for d in distances if BOX_DIST_MIN <= d <= BOX_DIST_MAX]
print(f"\n2️⃣ КОРОБКА ({BOX_DIST_MIN}-{BOX_DIST_MAX} мм):")
print(f"   Точек: {len(box_points)}")
if box_points:
    print(f"   Диапазон: {min(box_points)} - {max(box_points)} мм")
    print(f"   Среднее: {sum(box_points) / len(box_points):.0f} мм")
    print(f"   Высота коробки: {FLOOR_LEVEL - min(box_points)} - {FLOOR_LEVEL - max(box_points)} мм")
else:
    print("   ❌ НЕТ ТОЧЕК КОРОБКИ!")

# Категория 3: Пол (2542-2742 мм)
floor_points = [d for d in distances if BOX_DIST_MAX < d <= FLOOR_LEVEL + 50]
print(f"\n3️⃣ ПОЛ ({BOX_DIST_MAX}-{FLOOR_LEVEL+50} мм):")
print(f"   Точек: {len(floor_points)}")
if floor_points:
    print(f"   Диапазон: {min(floor_points)} - {max(floor_points)} мм")
    print(f"   Среднее: {sum(floor_points) / len(floor_points):.0f} мм")

# Категория 4: Дальний шум (> пола)
noise = [d for d in distances if d > FLOOR_LEVEL + 50]
print(f"\n4️⃣ ДАЛЬНИЙ ШУМ (> {FLOOR_LEVEL+50} мм):")
print(f"   Точек: {len(noise)}")
if noise:
    print(f"   Диапазон: {min(noise)} - {max(noise)} мм")

# 5. Гистограмма для коробки
print("\n" + "-" * 80)
print("📊 ГИСТОГРАММА КОРОБКИ (шаг 50 мм):")
print("-" * 80)

if box_points:
    bins = {}
    for d in box_points:
        bin_key = int(d / 50) * 50
        bins[bin_key] = bins.get(bin_key, 0) + 1

    sorted_bins = sorted(bins.items(), key=lambda x: x[1], reverse=True)
    for bin_val, count in sorted_bins[:10]:
        bar = "█" * min(count, 40)
        print(f"   {bin_val:>5} мм: {count:>3} точек {bar}")
else:
    print("   ❌ Нет точек коробки!")

# 6. Вывод
print("\n" + "=" * 80)
print("📊 ИТОГ:")
print("=" * 80)

print(f"""
    📦 КОРОБКА:
        Всего точек: {len(box_points)}
        Диапазон расстояний: {min(box_points) if box_points else 0} - {max(box_points) if box_points else 0} мм
        Среднее расстояние: {sum(box_points) / len(box_points):.0f} мм
        Высота коробки: {FLOOR_LEVEL - max(box_points) if box_points else 0} - {FLOOR_LEVEL - min(box_points) if box_points else 0} мм

    🧱 СТЕНЫ НИШИ:
        Точек: {len(walls)}
        Диапазон: {min(walls) if walls else 0} - {max(walls) if walls else 0} мм

    🏗️ ПОЛ:
        Точек: {len(floor_points)}
        Уровень: {FLOOR_LEVEL} мм

    📊 ОБЩАЯ СТАТИСТИКА:
        Всего точек: {len(distances)}
        Из них коробка: {len(box_points)} ({len(box_points) / len(distances) * 100:.1f}%)
        Стены ниши: {len(walls)} ({len(walls) / len(distances) * 100:.1f}%)
        Пол: {len(floor_points)} ({len(floor_points) / len(distances) * 100:.1f}%)
""")

# 7. Рекомендация
if len(box_points) < 10:
    print("\n⚠️ ВНИМАНИЕ: МАЛО ТОЧЕК КОРОБКИ!")
    print(f"   Всего {len(box_points)} точек (нужно минимум 10-15)")
    print("\n   Возможные причины:")
    print("   1. Коробка стоит под углом к лидару")
    print("   2. Коробка слишком маленькая")
    print("   3. Лидар видит только край коробки")
    print("   4. Угол сканирования слишком узкий для этой коробки")
elif len(box_points) < 30:
    print(f"\n✅ Нормально: {len(box_points)} точек коробки")
    print("   (достаточно для определения, но хотелось бы больше)")
else:
    print(f"\n✅ ОТЛИЧНО: {len(box_points)} точек коробки!")

sock.close()
print("\n🔌 Отключено")