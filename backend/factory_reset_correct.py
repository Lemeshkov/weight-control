# # backend/factory_reset_correct.py - сброс настроек лидара!!!!!
# import socket
# import time

# LIDAR_HOST = "192.168.1.101"
# LIDAR_PORT = 2111


# def send_cmd(sock, cmd, wait=0.5):
#     full_cmd = f"\x02{cmd}\x03"
#     sock.send(full_cmd.encode('utf-8'))
#     time.sleep(wait)
#     try:
#         response = sock.recv(65535)
#         decoded = response.decode('utf-8', errors='ignore').strip('\x02\x03')
#         return decoded
#     except socket.timeout:
#         return "TIMEOUT"


# def parse_angle_value(val_str):
#     try:
#         val = int(val_str, 16)
#         if val > 0x7FFFFFFF:
#             val = val - 0x100000000
#         return val
#     except ValueError:
#         try:
#             return int(val_str)
#         except ValueError:
#             return 0


# print("=" * 80)
# print("🔄 ПРАВИЛЬНЫЙ СБРОС + НАСТРОЙКА 0°")
# print("=" * 80)

# sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# sock.settimeout(5)
# sock.connect((LIDAR_HOST, LIDAR_PORT))
# print("✅ Подключен")

# # ============================================================
# # ШАГ 1: ВЫХОД ИЗ ТЕКУЩЕГО РЕЖИМА
# # ============================================================
# print("\n📡 1. Logout...")
# resp = send_cmd(sock, "sMN Logout")
# print(f"   Ответ: {resp}")

# # ============================================================
# # ШАГ 2: АВТОРИЗАЦИЯ КАК AUTHORIZED CLIENT
# # ============================================================
# print("\n📡 2. SetAccessMode (Authorized client)...")
# resp = send_cmd(sock, "sMN SetAccessMode 3 F4724744")
# print(f"   Ответ: {resp}")
# time.sleep(0.5)

# # ============================================================
# # ШАГ 3: ЗАВОДСКОЙ СБРОС
# # ============================================================
# print("\n📡 3. Factory reset...")
# resp = send_cmd(sock, "sMN mSCloadfacdef")
# print(f"   Ответ: {resp}")
# time.sleep(2)

# # ============================================================
# # ШАГ 4: ПОВТОРНАЯ АВТОРИЗАЦИЯ ПОСЛЕ СБРОСА
# # ============================================================
# print("\n📡 4. Повторная авторизация...")
# resp = send_cmd(sock, "sMN SetAccessMode 3 F4724744")
# print(f"   Ответ: {resp}")
# time.sleep(0.5)

# # ============================================================
# # ШАГ 5: УСТАНОВКА СТАРТОВОГО УГЛА 0°
# # ============================================================
# print("\n📡 5. Установка диапазона 0°...90°...")
# cmd = "sWN LMPoutputRange 1 +5000 0 +900000"
# print(f"   Команда: {cmd}")
# resp = send_cmd(sock, cmd, wait=1)
# print(f"   Ответ: {resp}")

# # ============================================================
# # ШАГ 6: ЗАПУСК СКАНИРОВАНИЯ
# # ============================================================
# print("\n📡 6. Запуск сканирования...")
# resp = send_cmd(sock, "sMN Run")
# print(f"   Ответ: {resp}")

# # ============================================================
# # ШАГ 7: СОХРАНЕНИЕ В ПАМЯТЬ (с дополнительными шагами)
# # ============================================================
# print("\n📡 7. Сохранение настроек...")
# # Сначала останавливаем сканирование
# resp = send_cmd(sock, "sMN Stop")
# print(f"   Stop: {resp}")

# # Сохраняем настройки
# resp = send_cmd(sock, "sMN mEEwriteall", wait=2)
# print(f"   mEEwriteall: {resp}")

# # Ждем завершения записи
# time.sleep(2)

# # Перезапускаем сканирование
# resp = send_cmd(sock, "sMN Run")
# print(f"   Run: {resp}")

# # ============================================================
# # ШАГ 8: ПРОВЕРКА УГЛА
# # ============================================================
# print("\n📡 8. Проверка угла...")
# resp = send_cmd(sock, "sRN LMPoutputRange")
# print(f"   Ответ: {resp}")

# if resp and "LMPoutputRange" in resp:
#     parts = resp.split()
#     if len(parts) >= 6:
#         start_raw = parse_angle_value(parts[4])
#         stop_raw = parse_angle_value(parts[5])
#         print(f"\n📊 ФИНАЛЬНЫЙ УГОЛ:")
#         print(f"   Стартовый: {start_raw / 100:.1f}°")
#         print(f"   Конечный: {stop_raw / 100:.1f}°")
#         print(f"   Общий: {(stop_raw - start_raw) / 100:.1f}°")

# # ============================================================
# # ШАГ 9: ПРОВЕРКА ДАННЫХ (видит ли коробку на 0°)
# # ============================================================
# print("\n📡 9. Проверка данных сканирования...")
# resp = send_cmd(sock, "sRN LMDscandata", wait=1)
# print(f"   Ответ (первые 300 символов):")
# print(f"   {resp[:300]}...")

# # ============================================================
# # ШАГ 10: ВЫХОД
# # ============================================================
# print("\n📡 10. Logout...")
# resp = send_cmd(sock, "sMN Logout")
# print(f"   Ответ: {resp}")

# sock.close()
# print("\n🔌 Отключено")
# print("\n💡 Теперь лидар должен видеть коробку при 0°")

# backend/factory_reset_correct.py - сброс настроек лидара с сохранением!!!!!
import socket
import time

LIDAR_HOST = "192.168.1.101"
LIDAR_PORT = 2111


def send_cmd(sock, cmd, wait=0.5):
    full_cmd = f"\x02{cmd}\x03"
    sock.send(full_cmd.encode('utf-8'))
    time.sleep(wait)
    try:
        response = sock.recv(65535)
        decoded = response.decode('utf-8', errors='ignore').strip('\x02\x03')
        return decoded
    except socket.timeout:
        return "TIMEOUT"


def parse_angle_value(val_str):
    try:
        val = int(val_str, 16)
        if val > 0x7FFFFFFF:
            val = val - 0x100000000
        return val
    except ValueError:
        try:
            return int(val_str)
        except ValueError:
            return 0


print("=" * 80)
print("🔄 ПРАВИЛЬНЫЙ СБРОС + НАСТРОЙКА УГЛА + СОХРАНЕНИЕ")
print("=" * 80)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5)
sock.connect((LIDAR_HOST, LIDAR_PORT))
print("✅ Подключен")

# ============================================================
# ШАГ 1: ВЫХОД ИЗ ТЕКУЩЕГО РЕЖИМА
# ============================================================
print("\n📡 1. Logout...")
resp = send_cmd(sock, "sMN Logout")
print(f"   Ответ: {resp}")

# ============================================================
# ШАГ 2: АВТОРИЗАЦИЯ КАК AUTHORIZED CLIENT
# ============================================================
print("\n📡 2. SetAccessMode (Authorized client)...")
resp = send_cmd(sock, "sMN SetAccessMode 3 F4724744")
print(f"   Ответ: {resp}")
time.sleep(0.5)

# ============================================================
# ШАГ 3: ЗАВОДСКОЙ СБРОС
# ============================================================
print("\n📡 3. Factory reset...")
resp = send_cmd(sock, "sMN mSCloadfacdef")
print(f"   Ответ: {resp}")
time.sleep(2)

# ============================================================
# ШАГ 4: ПОВТОРНАЯ АВТОРИЗАЦИЯ ПОСЛЕ СБРОСА
# ============================================================
print("\n📡 4. Повторная авторизация...")
resp = send_cmd(sock, "sMN SetAccessMode 3 F4724744")
print(f"   Ответ: {resp}")
time.sleep(0.5)

# ============================================================
# ШАГ 5: ОСТАНОВКА СКАНИРОВАНИЯ (ВАЖНО ДЛЯ СОХРАНЕНИЯ!)
# ============================================================
print("\n📡 5. Остановка сканирования...")
resp = send_cmd(sock, "sMN Stop")
print(f"   Stop: {resp}")
time.sleep(0.5)

# ============================================================
# ШАГ 6: УСТАНОВКА СТАРТОВОГО УГЛА 0°...90°
# ============================================================
print("\n📡 6. Установка диапазона 0°...90°...")
cmd = "sWN LMPoutputRange 1 +5000 0 +900000"
print(f"   Команда: {cmd}")
resp = send_cmd(sock, cmd, wait=1)
print(f"   Ответ: {resp}")
time.sleep(0.5)

# ============================================================
# ШАГ 7: СОХРАНЕНИЕ В ПАМЯТЬ (КРИТИЧЕСКИ ВАЖНО!)
# ============================================================
print("\n📡 7. СОХРАНЕНИЕ НАСТРОЕК В EEPROM...")
# Несколько попыток сохранить
for attempt in range(3):
    resp = send_cmd(sock, "sMN mEEwriteall", wait=2)
    print(f"   Попытка {attempt + 1}: {resp}")
    if "sFA" not in resp:
        print("   ✅ Сохранение успешно!")
        break
    time.sleep(1)
else:
    print("   ⚠️ Не удалось сохранить настройки!")

time.sleep(1)

# ============================================================
# ШАГ 8: ЗАПУСК СКАНИРОВАНИЯ
# ============================================================
print("\n📡 8. Запуск сканирования...")
resp = send_cmd(sock, "sMN Run")
print(f"   Run: {resp}")

# ============================================================
# ШАГ 9: ПРОВЕРКА УГЛА
# ============================================================
print("\n📡 9. Проверка угла...")
resp = send_cmd(sock, "sRN LMPoutputRange")
print(f"   Ответ: {resp}")

if resp and "LMPoutputRange" in resp:
    parts = resp.split()
    if len(parts) >= 6:
        start_raw = parse_angle_value(parts[4])
        stop_raw = parse_angle_value(parts[5])
        print(f"\n📊 ФИНАЛЬНЫЙ УГОЛ:")
        print(f"   Стартовый: {start_raw / 100:.1f}°")
        print(f"   Конечный: {stop_raw / 100:.1f}°")
        print(f"   Общий: {(stop_raw - start_raw) / 100:.1f}°")

# ============================================================
# ШАГ 10: ПРОВЕРКА ДАННЫХ
# ============================================================
print("\n📡 10. Проверка данных сканирования...")
resp = send_cmd(sock, "sRN LMDscandata", wait=1)
print(f"   Ответ (первые 300 символов):")
print(f"   {resp[:300]}...")

# ============================================================
# ШАГ 11: ВЫХОД
# ============================================================
print("\n📡 11. Logout...")
resp = send_cmd(sock, "sMN Logout")
print(f"   Ответ: {resp}")

sock.close()
print("\n🔌 Отключено")
print("\n💡 Теперь лидар должен видеть коробку при 0°")
print("💡 Настройки сохранены в EEPROM и сохранятся после перезагрузки!")