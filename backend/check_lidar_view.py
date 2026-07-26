# backend/check_lidar_view.py

"""
Проверка - что видит лидар?
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
print("🔍 ЧТО ВИДИТ ЛИДАР?")
print("="*70)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5)
sock.connect((LIDAR_HOST, LIDAR_PORT))
print("✅ Подключен")

# Авторизация
resp = send_cmd(sock, "sMN SetAccessMode 3 F4724744")
print(f"Авторизация: {resp}")
time.sleep(0.2)

# Получаем данные
resp = send_cmd(sock, "sRN LMDscandata")

if resp and "DIST1" in resp:
    parts = resp.split()
    for i, part in enumerate(parts):
        if part == "DIST1":
            j = i + 1
            skip = 0
            while j < len(parts) and skip < 4:
                j += 1
                skip += 1

            points = []
            while j < len(parts) and parts[j] not in ["RSSI1", "RSSI2", "DIST2", "DEVICE"]:
                try:
                    value = int(parts[j], 16)
                    if value > 0x7FFFFFFF:
                        value = value - 0x100000000
                    if value > 0:
                        points.append(value)
                except:
                    pass
                j += 1
            break

print(f"\n📊 ВСЕГО ТОЧЕК: {len(points)}")

if points:
    print(f"\n📊 РАСПРЕДЕЛЕНИЕ:")
    print(f"   Min: {min(points)} мм")
    print(f"   Max: {max(points)} мм")
    print(f"   Avg: {sum(points)/len(points):.0f} мм")
    print(f"   Значения: {sorted(points)}")

    # Анализ
    if len(points) <= 5:
        print("\n⚠️ ЛИДАР ВИДИТ ТОЛЬКО 5 ТОЧЕК!")
        print("   Это значит, что в зоне сканирования НЕТ ОБЪЕКТОВ")
        print("   Возможные причины:")
        print("   1. Коробка стоит ПОД лидаром (не видна)")
        print("   2. Коробка слишком далеко (>30 м)")
        print("   3. Коробка слишком близко (<0.5 м)")
        print("   4. Луч лидара перекрыт")
        print("   5. Лидар смотрит в пустоту")
    elif len(points) < 50:
        print("\n⚠️ ЛИДАР ВИДИТ МАЛО ТОЧЕК")
        print(f"   {len(points)} точек - возможно, объект не в центре")
    else:
        print(f"\n✅ ЛИДАР ВИДИТ ОБЪЕКТ: {len(points)} точек")
        if min(points) < 1500:
            print(f"   Объект на {min(points)} мм - СЛИШКОМ БЛИЗКО!")
        elif min(points) < 2500:
            print(f"   Объект на {min(points)} мм - ХОРОШО!")

sock.close()
print("\n🔌 Отключено")