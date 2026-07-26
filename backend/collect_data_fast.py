# backend/collect_data_fast.py

"""
Быстрый сбор данных - использует текущее соединение без переподключения
"""
import socket
import time
import json
from datetime import datetime
from collections import Counter

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

def get_angle(sock):
    """Получить текущий угол"""
    resp = send_cmd(sock, "sRN LMPoutputRange")
    if resp and "LMPoutputRange" in resp:
        parts = resp.split()
        if len(parts) >= 6:
            try:
                start_raw = int(parts[4], 16) if 'FFFF' in parts[4] else int(parts[4])
                stop_raw = int(parts[5], 16) if 'FFFF' in parts[5] else int(parts[5])

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

def parse_distances(raw_data):
    """Парсинг расстояний из сырых данных"""
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
                        if 1000 <= value <= 3000:
                            distances.append(value)
                except ValueError:
                    pass
                j += 1
            break

    return distances

print("="*70)
print("📊 БЫСТРЫЙ СБОР ДАННЫХ")
print("="*70)

# Подключаемся
print("\n🔌 Подключение...")
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5)
sock.connect((LIDAR_HOST, LIDAR_PORT))
print(f"✅ Подключен к {LIDAR_HOST}:{LIDAR_PORT}")

# Проверяем угол
print("\n📡 Проверка угла...")
angle = get_angle(sock)
if angle:
    print(f"   Стартовый: {angle['start']:.1f}°")
    print(f"   Конечный: {angle['stop']:.1f}°")
    print(f"   Общий: {angle['total']:.1f}°")

    if angle['total'] != 50:
        print(f"\n⚠️ Угол {angle['total']:.1f}° не 50°!")
        print(f"   Сначала запустите: python set_angle.py")
        sock.close()
        exit()

# Получаем данные сканирования
print("\n📡 Получение данных...")
full_cmd = f"\x02sRN LMDscandata\x03"
sock.send(full_cmd.encode('utf-8'))
time.sleep(0.3)
response = sock.recv(65535)
raw_data = response.decode('utf-8', errors='ignore').strip('\x02\x03')

# Парсим
distances = parse_distances(raw_data)
print(f"\n📊 Получено точек: {len(distances)}")

if not distances:
    print("❌ Нет данных!")
    sock.close()
    exit()

# Анализ
print("\n" + "-"*70)
print("📊 СТАТИСТИКА")
print("-"*70)

print(f"   Всего точек: {len(distances)}")
print(f"   Min: {min(distances)} мм")
print(f"   Max: {max(distances)} мм")
print(f"   Avg: {sum(distances)/len(distances):.0f} мм")

# Бин-гистограмма
bins = {}
for d in distances:
    bin_key = int(d / 50) * 50
    bins[bin_key] = bins.get(bin_key, 0) + 1

print("\n📊 ТОП-10 БИНОВ:")
sorted_bins = sorted(bins.items(), key=lambda x: x[1], reverse=True)
for i, (bin_val, count) in enumerate(sorted_bins[:10]):
    bar = "█" * min(40, count)
    pct = count / len(distances) * 100
    print(f"   #{i+1}: {bin_val:>5} мм -> {count:>3} ({pct:>5.1f}%) {bar}")

# Поиск объекта
FLOOR = 2792
object_points = [d for d in distances if d < 2700]

print("\n" + "-"*70)
print("📦 ОБЪЕКТ")
print("-"*70)

if object_points:
    min_obj = min(object_points)
    max_obj = max(object_points)
    height = FLOOR - min_obj

    print(f"\n   Точек: {len(object_points)}")
    print(f"   Min: {min_obj} мм")
    print(f"   Max: {max_obj} мм")
    print(f"   Высота от пола: {height} мм ({height/10:.1f} см)")

    # Определяем статус
    if len(object_points) <= 10:
        status = "🟢 ПУСТО"
    elif len(object_points) >= 15:
        status = "🟠 ЗАПОЛНЕНО"
    else:
        status = "🟡 ПРОМЕЖУТОЧНОЕ"

    print(f"   Статус: {status}")

    # Проверка коробки M
    print(f"\n   📦 КОРОБКА M (ожидается 370 мм):")
    if 320 <= height <= 400:
        print(f"      ✅ СООТВЕТСТВУЕТ! ({height:.0f} мм)")
    elif height < 200:
        print(f"      ⚠️ СЛИШКОМ НИЗКАЯ ({height:.0f} мм) - возможно, пустая")
    else:
        print(f"      ❌ НЕ СООТВЕТСТВУЕТ ({height:.0f} мм) - ожидается 370 мм")

    # Показываем реальные расстояния со смещением
    print(f"\n   💡 Если нужна калибровка:")
    print(f"      Реальное расстояние = {min_obj} + 1000 = {min_obj + 1000} мм")
    print(f"      Тогда высота = {FLOOR} - {min_obj + 1000} = {FLOOR - (min_obj + 1000)} мм")

else:
    print("\n   ❌ Объект не обнаружен!")

# Сохраняем
data = {
    "timestamp": datetime.now().isoformat(),
    "angle": angle,
    "points_count": len(distances),
    "object_points": len(object_points),
    "object_height": height if object_points else 0,
    "bins": sorted_bins[:10],
    "sample": distances[:50]
}

filename = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
with open(filename, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"\n💾 Сохранено: {filename}")

sock.close()
print("\n🔌 Отключено")