# backend/fix_distance_offset.py

"""
Исправление смещения расстояния (Distance Offset)
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

print("="*80)
print("🔧 ИСПРАВЛЕНИЕ СМЕЩЕНИЯ РАССТОЯНИЯ")
print("="*80)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5)
sock.connect((LIDAR_HOST, LIDAR_PORT))
print("✅ Подключен")

# 1. Выход
print("\n📡 1. Logout...")
resp = send_cmd(sock, "sMN Logout")
print(f"   Ответ: {resp}")
time.sleep(0.2)

# 2. Авторизация
print("\n📡 2. SetAccessMode...")
resp = send_cmd(sock, "sMN SetAccessMode 3 F4724744")
print(f"   Ответ: {resp}")
time.sleep(0.2)

# 3. Проверка текущих настроек расстояния
print("\n📡 3. Проверка настроек расстояния...")
resp = send_cmd(sock, "sRN LMDscalecfg")
print(f"   Ответ: {resp}")
time.sleep(0.2)

# 4. Сброс смещения расстояния (устанавливаем 0)
print("\n📡 4. Сброс смещения расстояния...")
cmd = "sWN LMDscalecfg 1 1 0"
print(f"   Команда: {cmd}")
resp = send_cmd(sock, cmd)
print(f"   Ответ: {resp}")
time.sleep(0.2)

# 5. Проверка после сброса
print("\n📡 5. Проверка после сброса...")
resp = send_cmd(sock, "sRN LMDscalecfg")
print(f"   Ответ: {resp}")
time.sleep(0.2)

# 6. Перезапуск
print("\n📡 6. Перезапуск...")
resp = send_cmd(sock, "sMN Run")
print(f"   Ответ: {resp}")
time.sleep(0.2)

# 7. Проверка данных
print("\n📡 7. Проверка данных...")
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

    print(f"\n📊 ТОЧКИ ПОСЛЕ СБРОСА:")
    print(f"   Всего: {len(points)}")
    if points:
        print(f"   Значения: {sorted(points)}")
        print(f"   Min: {min(points)} мм")
        print(f"   Max: {max(points)} мм")

        if min(points) > 2000:
            print(f"\n✅ УСПЕХ! Лидар видит объект на {min(points)} мм!")
        else:
            print(f"\n⚠️ Лидар все еще видит объект на {min(points)} мм")
            print(f"   Возможно, нужна физическая настройка лидара")

sock.close()
print("\n🔌 Отключено")