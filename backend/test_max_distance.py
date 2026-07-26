# backend/test_max_distance.py
"""
Тест максимальной дальности лидара - ИСПРАВЛЕННЫЙ
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


def parse_all_distances_correct(raw_data):
    """
    ПРАВИЛЬНЫЙ парсинг расстояний
    Ищет начало данных по значениям, а не по фиксированному смещению
    """
    if not raw_data:
        return []

    parts = raw_data.split()
    distances = []

    for i, part in enumerate(parts):
        if part == "DIST1":
            j = i + 1

            # Пропускаем служебные поля, пока не найдем начало данных
            # В LMS511 служебные поля могут быть разного размера
            found_data_start = False
            max_skip = 15  # максимум служебных полей
            skip_count = 0

            while j < len(parts) and skip_count < max_skip:
                try:
                    # Пробуем прочитать как число
                    test_val = int(parts[j], 16)
                    if test_val > 0x7FFFFFFF:
                        test_val = test_val - 0x100000000

                    # Если значение похоже на расстояние (100-3000 мм) - это начало данных!
                    if 100 < test_val < 3000:
                        # Проверяем, что следующее значение тоже похоже на расстояние
                        if j + 1 < len(parts):
                            try:
                                next_val = int(parts[j + 1], 16)
                                if next_val > 0x7FFFFFFF:
                                    next_val = next_val - 0x100000000
                                if 100 < next_val < 3000:
                                    found_data_start = True
                                    break
                            except:
                                pass
                except:
                    pass

                j += 1
                skip_count += 1

            # Если нашли начало данных - читаем расстояния
            if found_data_start:
                while j < len(parts) and parts[j] not in ["RSSI1", "RSSI2", "DIST2", "DEVICE"]:
                    try:
                        hex_val = parts[j].strip()
                        if hex_val:
                            value = int(hex_val, 16)
                            if value > 0x7FFFFFFF:
                                value = value - 0x100000000
                            if 0 < value < 50000:
                                distances.append(value)
                    except ValueError:
                        pass
                    j += 1
            break

    return distances


def debug_raw_response(raw_data):
    """Показывает структуру ответа для отладки"""
    if not raw_data:
        return

    parts = raw_data.split()
    print("\n📄 ОТВЕТ ЛИДАРА (разбор):")
    print(f"   Всего частей: {len(parts)}")

    # Находим DIST1
    for i, part in enumerate(parts):
        if part == "DIST1":
            print(f"\n   DIST1 найден на позиции {i}")
            print(f"   Следующие 20 элементов:")

            for idx in range(i + 1, min(i + 21, len(parts))):
                try:
                    val = int(parts[idx], 16)
                    if val > 0x7FFFFFFF:
                        signed = val - 0x100000000
                    else:
                        signed = val

                    # Определяем тип значения
                    if 100 < signed < 3000:
                        marker = "✅ РАССТОЯНИЕ"
                    elif signed == 0:
                        marker = "(ноль)"
                    elif signed < 0:
                        marker = f"(отриц: {signed})"
                    else:
                        marker = f"(число: {signed})"

                    print(f"      [{idx}] {parts[idx]:>8} = {signed:>6} мм {marker}")
                except:
                    print(f"      [{idx}] {parts[idx]:>8} = НЕ HEX")
            break


print("=" * 80)
print("📏 ТЕСТ МАКСИМАЛЬНОЙ ДАЛЬНОСТИ (ИСПРАВЛЕННЫЙ)")
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
resp = send_cmd(sock, "sRN LMDscandata", wait=1)

# Отладочный вывод
debug_raw_response(resp)

# Правильный парсинг
print("\n" + "-" * 80)
print("📊 РЕЗУЛЬТАТЫ ПАРСИНГА")
print("-" * 80)

distances = parse_all_distances_correct(resp)

print(f"\n   Всего точек: {len(distances)}")

if distances:
    print(f"   Минимальное: {min(distances)} мм")
    print(f"   Максимальное: {max(distances)} мм")
    print(f"   Среднее: {sum(distances) / len(distances):.0f} мм")

    # Проверяем распределение
    print(f"\n   Распределение по диапазонам:")
    ranges = [
        (0, 500, "Стены ниши"),
        (500, 1000, "Ближняя зона"),
        (1000, 1500, "Зона 1"),
        (1500, 2000, "Зона 2"),
        (2000, 2500, "Зона 3"),
        (2500, 2742, "Пол"),
        (2742, 99999, "За полом"),
    ]

    for low, high, label in ranges:
        count = len([d for d in distances if low <= d < high])
        if count > 0:
            bar = "█" * min(count, 50)
            print(f"      {label:15} ({low:>4}-{high:>4} мм): {count:>4} точек {bar}")

    # Проверяем наличие пола и коробки
    floor_points = [d for d in distances if 2700 <= d <= 2800]
    box_points = [d for d in distances if 2200 <= d <= 2600]
    wall_points = [d for d in distances if d < 500]

    print(f"\n   📦 ТОЧКИ КОРОБКИ (2200-2600 мм): {len(box_points)}")
    print(f"   🏗️ ТОЧКИ ПОЛА (2700-2800 мм): {len(floor_points)}")
    print(f"   🧱 ТОЧКИ СТЕН НИШИ (<500 мм): {len(wall_points)}")

    if floor_points:
        print(f"\n✅ ЛИДАР ВИДИТ ПОЛ! Диапазон: {min(floor_points)}-{max(floor_points)} мм")

    if box_points:
        print(f"✅ КОРОБКА ВИДНА! Диапазон: {min(box_points)}-{max(box_points)} мм")
        print(f"   Высота коробки: {min(floor_points) - max(box_points) if floor_points else '?'} мм")

    if not floor_points and not box_points:
        print("\n⚠️ ЛИДАР НЕ ВИДИТ ПОЛ И КОРОБКУ!")
        print("   Проверьте настройки дальности в SOPAS ET")

sock.close()
print("\n🔌 Отключено")