# backend/correct_parse.py
"""
ПРАВИЛЬНЫЙ парсинг данных LMS511
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
    except socket.timeout:
        return "TIMEOUT"


def parse_distances_correct(raw_data):
    """
    ПРАВИЛЬНЫЙ парсинг расстояний из LMDscandata
    Пропускаем 4 служебных значения после DIST1
    """
    if not raw_data:
        return []

    parts = raw_data.split()
    distances = []

    for i, part in enumerate(parts):
        if part == "DIST1":
            j = i + 1

            # ПРОПУСКАЕМ 4 СЛУЖЕБНЫХ ЗНАЧЕНИЯ!
            # 1. Количество сканов
            # 2. Номер скана
            # 3. Количество точек (может быть отрицательным)
            # 4. Разрешение
            j += 4

            # Теперь читаем ТОЛЬКО расстояния
            while j < len(parts) and parts[j] not in ["RSSI1", "RSSI2", "DIST2", "DEVICE"]:
                try:
                    hex_val = parts[j].strip()
                    if hex_val:
                        value = int(hex_val, 16)
                        # Конвертируем в миллиметры
                        if value > 0x7FFFFFFF:
                            value = value - 0x100000000
                        # Фильтруем разумные значения
                        if 0 < value < 50000:
                            distances.append(value)
                except ValueError:
                    pass
                j += 1
            break

    return distances


def parse_scan_info(raw_data):
    """Парсит служебную информацию из LMDscandata"""
    if not raw_data:
        return None

    parts = raw_data.split()

    for i, part in enumerate(parts):
        if part == "DIST1" and i + 4 < len(parts):
            try:
                # Служебные поля
                scan_count = int(parts[i+1], 16)
                scan_number = int(parts[i+2], 16)
                points_raw = int(parts[i+3], 16)
                resolution_raw = int(parts[i+4], 16)

                # Если количество точек отрицательное - конвертируем
                if points_raw > 0x7FFFFFFF:
                    points_count = points_raw - 0x100000000
                else:
                    points_count = points_raw

                return {
                    'scan_count': scan_count,
                    'scan_number': scan_number,
                    'points_count': abs(points_count),  # берем по модулю
                    'resolution': resolution_raw / 10000,
                    'resolution_raw': resolution_raw
                }
            except:
                pass

    return None


print("=" * 80)
print("📊 ПРАВИЛЬНЫЙ ПАРСИНГ ДАННЫХ LMS511")
print("=" * 80)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5)

try:
    sock.connect((LIDAR_HOST, LIDAR_PORT))
    print(f"✅ Подключен к {LIDAR_HOST}:{LIDAR_PORT}")
except Exception as e:
    print(f"❌ Ошибка подключения: {e}")
    exit()

# Авторизация
print("\n📡 Авторизация...")
send_cmd(sock, "sMN Logout")
time.sleep(0.2)
send_cmd(sock, "sMN SetAccessMode 3 F4724744")
time.sleep(0.3)
send_cmd(sock, "sMN Run")
time.sleep(0.3)

# Получаем данные
print("\n📡 Получение данных...")
raw_response = send_cmd(sock, "sRN LMDscandata", wait=1)

# Парсим служебную информацию
info = parse_scan_info(raw_response)
if info:
    print(f"\n📊 СЛУЖЕБНАЯ ИНФОРМАЦИЯ:")
    print(f"   Количество сканов: {info['scan_count']}")
    print(f"   Номер скана: {info['scan_number']}")
    print(f"   Количество точек: {info['points_count']}")
    print(f"   Разрешение: {info['resolution']:.4f}°")

# Парсим расстояния
distances = parse_distances_correct(raw_response)

print(f"\n📊 РЕЗУЛЬТАТЫ ПАРСИНГА:")
print(f"   Всего точек: {len(distances)}")

if distances:
    print(f"   Минимальное: {min(distances)} мм")
    print(f"   Максимальное: {max(distances)} мм")
    print(f"   Среднее: {sum(distances) / len(distances):.0f} мм")

    # Проверяем наличие пола и коробки
    floor_points = [d for d in distances if 2700 <= d <= 2800]
    box_points = [d for d in distances if 2200 <= d <= 2600]
    wall_points = [d for d in distances if d < 500]
    near_points = [d for d in distances if 500 <= d < 2000]

    print(f"\n📦 ТОЧКИ КОРОБКИ (2200-2600 мм): {len(box_points)}")
    if box_points:
        print(f"   Диапазон: {min(box_points)}-{max(box_points)} мм")

    print(f"🏗️ ТОЧКИ ПОЛА (2700-2800 мм): {len(floor_points)}")
    if floor_points:
        print(f"   Диапазон: {min(floor_points)}-{max(floor_points)} мм")

    print(f"🧱 ТОЧКИ СТЕН НИШИ (<500 мм): {len(wall_points)}")
    print(f"📏 ТОЧКИ БЛИЖНЕЙ ЗОНЫ (500-2000 мм): {len(near_points)}")

    # Если есть точки пола - лидар работает правильно!
    if floor_points:
        print("\n" + "=" * 80)
        print("✅ ЛИДАР ВИДИТ ПОЛ! Данные корректны!")
        print("=" * 80)
        print(f"   Уровень пола: {min(floor_points)}-{max(floor_points)} мм")
        print(f"   Ожидаемый уровень пола: 2742 мм")

        if box_points:
            print(f"\n✅ КОРОБКА ВИДНА! {len(box_points)} точек")
            print(f"   Высота коробки: {min(floor_points) - max(box_points)} мм")
        else:
            print("\n⚠️ КОРОБКА НЕ ВИДНА")
            print("   Возможно, коробка отсутствует или вне зоны сканирования")
    else:
        print("\n" + "=" * 80)
        print("⚠️ ЛИДАР НЕ ВИДИТ ПОЛ!")
        print("=" * 80)
        print("   Максимальное расстояние: {max(distances)} мм")
        print("   Ожидаемый уровень пола: 2742 мм")
        print("\n   Возможные причины:")
        print("   1. Лидар настроен на ближнюю зону (Near Field Mode)")
        print("   2. Неправильная калибровка дальности")
        print("   3. Лидар физически не достает до пола")

sock.close()
print("\n🔌 Отключено")