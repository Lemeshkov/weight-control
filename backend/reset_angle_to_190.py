# backend/reset_angle_to_190_fixed.py

"""
Сброс угла сканирования в стандартный 190° с правильным парсингом
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

print("="*70)
print("🔄 СБРОС УГЛА В 190° (-95°…+95°)")
print("="*70)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5)
sock.connect((LIDAR_HOST, LIDAR_PORT))
print("✅ Подключен")

# 1. Выход
print("\n📡 Logout...")
resp = send_cmd(sock, "sMN Logout")
print(f"   Ответ: {resp}")
time.sleep(0.2)

# 2. Авторизация
print("\n📡 SetAccessMode...")
resp = send_cmd(sock, "sMN SetAccessMode 3 F4724744")
print(f"   Ответ: {resp}")
time.sleep(0.2)

# 3. Установка 190° (СТАНДАРТНЫЙ УГОЛ)
print("\n📡 Установка 190° (-95°…+95°)...")
cmd = "sWN LMPoutputRange 1 +5000 -9500 +9500"
print(f"   Команда: {cmd}")
resp = send_cmd(sock, cmd)
print(f"   Ответ: {resp}")
time.sleep(0.2)

# 4. Запуск
print("\n📡 Run...")
resp = send_cmd(sock, "sMN Run")
print(f"   Ответ: {resp}")
time.sleep(0.2)

# 5. Проверка угла
print("\n📡 Проверка угла...")
resp = send_cmd(sock, "sRN LMPoutputRange")
print(f"   Ответ: {resp}")

if resp and "LMPoutputRange" in resp:
    parts = resp.split()
    print(f"\n📊 parts: {parts}")

    if len(parts) >= 6:
        resolution_raw = int(parts[3], 16)
        start_raw = parse_angle_value(parts[4])
        stop_raw = parse_angle_value(parts[5])

        print(f"\n📊 РЕЗУЛЬТАТ:")
        print(f"   Разрешение: {resolution_raw / 10000:.4f}°")
        print(f"   Стартовый: {start_raw / 100:.1f}°")
        print(f"   Конечный: {stop_raw / 100:.1f}°")
        print(f"   Общий: {(stop_raw - start_raw) / 100:.1f}°")

        if abs((stop_raw - start_raw) / 100 - 190) < 1:
            print("\n✅ УГОЛ 190° УСТАНОВЛЕН!")
        else:
            print(f"\n⚠️ УГОЛ {(stop_raw - start_raw) / 100:.1f}° НЕ 190°!")

sock.close()
print("\n🔌 Отключено")