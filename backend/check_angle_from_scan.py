# backend/check_angle_from_scan.py

"""
Проверка угла по количеству точек в сканировании
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

print("="*70)
print("🔍 ПРОВЕРКА УГЛА ПО ДАННЫМ СКАНИРОВАНИЯ")
print("="*70)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5)
sock.connect((LIDAR_HOST, LIDAR_PORT))
print("✅ Подключен")

# Авторизация
print("\n📡 Авторизация...")
resp = send_cmd(sock, "sMN SetAccessMode 3 F4724744")
print(f"   Ответ: {resp}")
time.sleep(0.2)

# Получаем данные
print("\n📡 Получение данных...")
resp = send_cmd(sock, "sRN LMDscandata")
print(f"   Ответ: {resp[:200]}...")

if resp and "DIST1" in resp:
    parts = resp.split()

    # Находим все точки
    all_points = []
    for i, part in enumerate(parts):
        if part == "DIST1":
            j = i + 1
            skip = 0
            while j < len(parts) and skip < 4:
                j += 1
                skip += 1

            while j < len(parts) and parts[j] not in ["RSSI1", "RSSI2", "DIST2", "DEVICE"]:
                try:
                    value = int(parts[j], 16)
                    if value > 0x7FFFFFFF:
                        value = value - 0x100000000
                    if 100 < value < 5000:
                        all_points.append(value)
                except:
                    pass
                j += 1
            break

    print(f"\n📊 Всего валидных точек: {len(all_points)}")

    if all_points:
        print(f"   Min: {min(all_points)} мм")
        print(f"   Max: {max(all_points)} мм")
        print(f"   Avg: {sum(all_points)/len(all_points):.0f} мм")

        # Проверяем распределение
        print(f"\n📊 Распределение точек по диапазонам:")
        ranges = {
            "0-100": 0,
            "100-500": 0,
            "500-1000": 0,
            "1000-1500": 0,
            "1500-2000": 0,
            "2000-2500": 0,
            "2500-2800": 0,
            "2800-3000": 0
        }

        for d in all_points:
            if d < 100: ranges["0-100"] += 1
            elif d < 500: ranges["100-500"] += 1
            elif d < 1000: ranges["500-1000"] += 1
            elif d < 1500: ranges["1000-1500"] += 1
            elif d < 2000: ranges["1500-2000"] += 1
            elif d < 2500: ranges["2000-2500"] += 1
            elif d < 2800: ranges["2500-2800"] += 1
            else: ranges["2800-3000"] += 1

        for name, count in ranges.items():
            if count > 0:
                bar = "█" * min(40, count)
                print(f"   {name}: {count:>3} {bar}")

        # Определяем угол по количеству точек
        # При 70° должно быть ~300-500 точек
        # При 50° ~200-350 точек
        # При 30° ~100-200 точек
        print(f"\n🎯 РЕКОМЕНДАЦИЯ:")
        if len(all_points) > 300:
            print(f"   ✅ Угол 70° (много точек: {len(all_points)})")
        elif len(all_points) > 200:
            print(f"   ⚠️ Угол 50° (средне: {len(all_points)})")
        elif len(all_points) > 100:
            print(f"   ⚠️ Угол 30° (мало: {len(all_points)})")
        else:
            print(f"   ❌ Угол меньше 30° или проблемы с лидаром ({len(all_points)})")

sock.close()
print("\n🔌 Отключено")