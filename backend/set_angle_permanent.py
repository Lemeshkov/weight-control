# backend/set_angle_permanent.py
"""
УСТАНОВКА УГЛА -35°...+35° С СОХРАНЕНИЕМ В EEPROM
Использует уровень доступа SERVICE для гарантированного сохранения
"""
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
print("🔧 УСТАНОВКА УГЛА -35°...+35° С СОХРАНЕНИЕМ")
print("=" * 80)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5)

try:
    sock.connect((LIDAR_HOST, LIDAR_PORT))
    print(f"✅ Подключен к {LIDAR_HOST}:{LIDAR_PORT}")
except Exception as e:
    print(f"❌ Ошибка подключения: {e}")
    print("Проверьте IP и порт лидара!")
    exit()

# ============================================================
# ШАГ 1: ВЫХОД
# ============================================================
print("\n📡 1. Logout...")
resp = send_cmd(sock, "sMN Logout")
print(f"   Ответ: {resp}")

# ============================================================
# ШАГ 2: АВТОРИЗАЦИЯ КАК SERVICE (БОЛЕЕ ВЫСОКИЙ УРОВЕНЬ)
# ============================================================
print("\n📡 2. SetAccessMode (SERVICE level)...")
# Пароль для Service: 81BE23AA (хеш от servicelevel)
resp = send_cmd(sock, "sMN SetAccessMode 2 81BE23AA")
print(f"   Ответ: {resp}")

if "sFA" in resp:
    print("   ⚠️ Пароль 81BE23AA не подошел, пробуем 'service'...")
    resp = send_cmd(sock, "sMN SetAccessMode 2 73657276696365")
    print(f"   Ответ: {resp}")

time.sleep(0.5)

# ============================================================
# ШАГ 3: ОСТАНОВКА СКАНИРОВАНИЯ
# ============================================================
print("\n📡 3. Остановка сканирования...")
resp = send_cmd(sock, "sMN Stop")
print(f"   Stop: {resp}")
time.sleep(0.5)

# ============================================================
# ШАГ 4: УСТАНОВКА УГЛА -35°...+35°
# ============================================================
print("\n📡 4. Установка угла -35°...+35°...")
cmd = "sWN LMPoutputRange 1 +5000 -3500 +3500"
print(f"   Команда: {cmd}")
resp = send_cmd(sock, cmd, wait=1)
print(f"   Ответ: {resp}")
time.sleep(0.5)

# ============================================================
# ШАГ 5: ПРОВЕРКА УГЛА ПОСЛЕ УСТАНОВКИ
# ============================================================
print("\n📡 5. Проверка угла после установки...")
resp = send_cmd(sock, "sRN LMPoutputRange")
print(f"   Ответ: {resp}")

if resp and "LMPoutputRange" in resp:
    parts = resp.split()
    if len(parts) >= 6:
        start_raw = parse_angle_value(parts[4])
        stop_raw = parse_angle_value(parts[5])
        print(f"\n   Текущий угол:")
        print(f"   Стартовый: {start_raw / 100:.1f}°")
        print(f"   Конечный: {stop_raw / 100:.1f}°")
        print(f"   Общий: {(stop_raw - start_raw) / 100:.1f}°")

# ============================================================
# ШАГ 6: СОХРАНЕНИЕ В EEPROM (С РАЗНЫМИ СПОСОБАМИ)
# ============================================================
print("\n📡 6. СОХРАНЕНИЕ В EEPROM...")
print("   (Это может занять несколько секунд)")

saved = False

# Попытка 1: mEEwriteall (стандартный)
print("\n   Попытка 1: mEEwriteall...")
resp = send_cmd(sock, "sMN mEEwriteall", wait=3)
print(f"   Ответ: {resp}")
if "sFA" not in resp:
    saved = True
    print("   ✅ Сохранение успешно!")

# Попытка 2: mEEwrite (если не сработало)
if not saved:
    print("\n   Попытка 2: mEEwrite...")
    resp = send_cmd(sock, "sMN mEEwrite", wait=3)
    print(f"   Ответ: {resp}")
    if "sFA" not in resp:
        saved = True
        print("   ✅ Сохранение успешно!")

# Попытка 3: mEEwriteall с другой командой
if not saved:
    print("\n   Попытка 3: mEEwriteall (с повторной авторизацией)...")
    # Переавторизация
    send_cmd(sock, "sMN SetAccessMode 2 81BE23AA", wait=0.5)
    resp = send_cmd(sock, "sMN mEEwriteall", wait=3)
    print(f"   Ответ: {resp}")
    if "sFA" not in resp:
        saved = True
        print("   ✅ Сохранение успешно!")

if not saved:
    print("\n   ⚠️ НЕ УДАЛОСЬ СОХРАНИТЬ НАСТРОЙКИ ЧЕРЕЗ ТЕРМИНАЛ!")
    print("   Используйте SOPAS ET для сохранения:")
    print("   1. Подключитесь к лидару")
    print("   2. Авторизуйтесь как Service (пароль: servicelevel)")
    print("   3. Настройте угол -35°...+35°")
    print("   4. Нажмите 'Save permanent'")

# ============================================================
# ШАГ 7: ЗАПУСК СКАНИРОВАНИЯ
# ============================================================
print("\n📡 7. Запуск сканирования...")
resp = send_cmd(sock, "sMN Run")
print(f"   Run: {resp}")

# ============================================================
# ШАГ 8: ФИНАЛЬНАЯ ПРОВЕРКА УГЛА
# ============================================================
print("\n📡 8. Финальная проверка угла...")
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
# ШАГ 9: ВЫХОД
# ============================================================
print("\n📡 9. Logout...")
resp = send_cmd(sock, "sMN Logout")
print(f"   Ответ: {resp}")

sock.close()
print("\n🔌 Отключено")

if saved:
    print("\n" + "=" * 80)
    print("✅ НАСТРОЙКИ УСПЕШНО СОХРАНЕНЫ В EEPROM!")
    print("   Угол -35°...+35° сохранен навсегда!")
    print("   Теперь настройки сохранятся после перезагрузки")
    print("=" * 80)
else:
    print("\n" + "=" * 80)
    print("⚠️ НАСТРОЙКИ НЕ СОХРАНИЛИСЬ В EEPROM!")
    print("   Используйте SOPAS ET для сохранения:")
    print("   1. Подключитесь к лидару")
    print("   2. Авторизуйтесь как Service (пароль: servicelevel)")
    print("   3. Настройте угол -35°...+35° в Output range")
    print("   4. Нажмите 'Save permanent' в меню LMS... → Parameter")
    print("=" * 80)

# ============================================================
# ШАГ 10: ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА ДАННЫХ
# ============================================================
if saved:
    print("\n📡 10. Дополнительная проверка (переподключение)...")
    time.sleep(2)

    try:
        sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock2.settimeout(5)
        sock2.connect((LIDAR_HOST, LIDAR_PORT))
        print("   ✅ Переподключено")

        send_cmd(sock2, "sMN SetAccessMode 3 F4724744", wait=0.5)
        resp = send_cmd(sock2, "sRN LMPoutputRange", wait=0.5)
        print(f"   Проверка угла: {resp}")

        sock2.close()
    except Exception as e:
        print(f"   ❌ Ошибка переподключения: {e}")