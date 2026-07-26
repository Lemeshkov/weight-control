# backend/set_correct_angle.py

"""
Правильная настройка угла сканирования лидара SICK LMS511
Использует проверенные HEX-команды
"""
import socket
import time

LIDAR_HOST = "192.168.1.101"
LIDAR_PORT = 2111

def send_cmd(sock, cmd, wait=0.3):
    """Отправка команды и получение ответа"""
    full_cmd = f"\x02{cmd}\x03"
    try:
        sock.send(full_cmd.encode('utf-8'))
        time.sleep(wait)
        response = sock.recv(65535)
        decoded = response.decode('utf-8', errors='ignore')
        decoded = decoded.strip('\x02\x03')
        return decoded
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None

def connect_to_lidar():
    """Подключение к лидару"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    sock.connect((LIDAR_HOST, LIDAR_PORT))
    print(f"✅ Подключен к {LIDAR_HOST}:{LIDAR_PORT}")
    return sock

def auth_lidar(sock):
    """Авторизация в лидаре"""
    print("\n📡 Авторизация...")

    resp = send_cmd(sock, "sMN Logout")
    print(f"   Logout: {resp[:50] if resp else 'None'}")
    time.sleep(0.2)

    resp = send_cmd(sock, "sMN SetAccessMode 3 F4724744")
    print(f"   SetAccessMode: {resp[:50] if resp else 'None'}")
    time.sleep(0.2)

    return resp

def set_angle(sock, angle_name, start_hex, stop_hex):
    """
    Установка угла сканирования с HEX-значениями

    Args:
        angle_name: название угла (для вывода)
        start_hex: HEX начального угла (например, FFFF1148 для -15°)
        stop_hex: HEX конечного угла (например, 1148 для +15°)
    """
    print(f"\n📡 Установка угла {angle_name}...")

    # Авторизация
    auth_lidar(sock)

    # Устанавливаем угол
    cmd = f"sWN LMPoutputRange 1 5000 {start_hex} {stop_hex}"
    print(f"   Команда: {cmd}")
    resp = send_cmd(sock, cmd)
    print(f"   Ответ: {resp[:50] if resp else 'None'}")
    time.sleep(0.2)

    # Запускаем сканирование
    resp = send_cmd(sock, "sMN Run")
    print(f"   Run: {resp[:50] if resp else 'None'}")
    time.sleep(0.2)

    return resp

def set_angle_20(sock):
    """20° (-10°…+10°)"""
    set_angle(sock, "20° (-10°…+10°)", "FFFF0B90", "0B90")

def set_angle_30(sock):
    """30° (-15°…+15°)"""
    set_angle(sock, "30° (-15°…+15°)", "FFFF1148", "1148")

def set_angle_40(sock):
    """40° (-20°…+20°)"""
    set_angle(sock, "40° (-20°…+20°)", "FFFF16A0", "16A0")

def set_angle_50(sock):
    """50° (-25°…+25°)"""
    set_angle(sock, "50° (-25°…+25°)", "FFFF1BF8", "1BF8")

def set_angle_60(sock):
    """60° (-30°…+30°)"""
    set_angle(sock, "60° (-30°…+30°)", "FFFF2120", "2120")

def get_current_angle(sock):
    """Получить текущий угол сканирования"""
    print("\n📡 Проверка текущего угла...")
    resp = send_cmd(sock, "sRN LMPoutputRange")
    print(f"   Ответ: {resp}")

    if resp and "LMPoutputRange" in resp:
        parts = resp.split()
        if len(parts) >= 6:
            try:
                # Парсим правильным способом (с делением на 100)
                resolution_raw = int(parts[3], 16)  # 1388 = 5000

                # Парсим начальный угол (HEX)
                start_hex = parts[4]
                if start_hex.startswith('FFFF'):
                    # Отрицательное число в HEX
                    start_raw = int(start_hex, 16)
                    if start_raw > 0x7FFFFFFF:
                        start_raw = start_raw - 0x100000000
                else:
                    start_raw = int(start_hex, 16)

                # Парсим конечный угол (HEX)
                stop_hex = parts[5]
                if stop_hex.startswith('FFFF'):
                    stop_raw = int(stop_hex, 16)
                    if stop_raw > 0x7FFFFFFF:
                        stop_raw = stop_raw - 0x100000000
                else:
                    stop_raw = int(stop_hex, 16)

                print(f"\n📊 ТЕКУЩИЙ УГОЛ:")
                print(f"   Разрешение: {resolution_raw / 10000:.4f}°")
                print(f"   Стартовый: {start_raw / 100:.1f}°")
                print(f"   Конечный: {stop_raw / 100:.1f}°")
                print(f"   Общий: {(stop_raw - start_raw) / 100:.1f}°")

                return {
                    "resolution": resolution_raw / 10000,
                    "start": start_raw / 100,
                    "stop": stop_raw / 100,
                    "total": (stop_raw - start_raw) / 100
                }
            except Exception as e:
                print(f"   ❌ Ошибка парсинга: {e}")

    return None

def main():
    print("\n" + "="*70)
    print("🔧 НАСТРОЙКА УГЛА СКАНИРОВАНИЯ ЛИДАРА")
    print("="*70)
    print("\n  1 - 20° (-10°…+10°)  (очень узкий)")
    print("  2 - 30° (-15°…+15°)  (узкий)")
    print("  3 - 40° (-20°…+20°)  (средний)")
    print("  4 - 50° (-25°…+25°)  (средний) ⭐ РЕКОМЕНДУЕТСЯ")
    print("  5 - 60° (-30°…+30°)  (широкий)")
    print("  6 - Показать текущий угол")
    print("  0 - Выход")
    print("")

    choice = input("Выберите: ").strip()

    try:
        sock = connect_to_lidar()

        if choice == "1":
            set_angle_20(sock)
        elif choice == "2":
            set_angle_30(sock)
        elif choice == "3":
            set_angle_40(sock)
        elif choice == "4":
            set_angle_50(sock)
        elif choice == "5":
            set_angle_60(sock)
        elif choice == "6":
            get_current_angle(sock)
        elif choice == "0":
            print("До свидания!")
            sock.close()
            return
        else:
            print("❌ Неверный выбор")
            sock.close()
            return

        # Показываем результат
        time.sleep(0.5)
        get_current_angle(sock)

        sock.close()
        print("\n🔌 Отключено")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()