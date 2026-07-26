# backend/set_angle.py

"""
Простая настройка угла сканирования лидара SICK LMS511
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

def parse_angle_value(val_str):
    """
    Парсит значение угла из строки.
    Поддерживает:
    - Десятичные: "2500"
    - HEX: "9C4", "DAC", "FFFFF63C"
    """
    val_str = val_str.strip()

    # Проверяем, является ли HEX (содержит буквы A-F)
    is_hex = any(c in val_str.upper() for c in 'ABCDEF')

    if is_hex:
        try:
            val = int(val_str, 16)
            # Если значение > 0x7FFFFFFF - это отрицательное число в доп. коде
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

def get_current_angle(sock):
    """Получить текущий угол"""
    resp = send_cmd(sock, "sRN LMPoutputRange")
    print(f"   Ответ: {resp}")

    if resp and "LMPoutputRange" in resp:
        parts = resp.split()
        if len(parts) >= 6:
            try:
                # Разрешение (всегда HEX)
                resolution_raw = int(parts[3], 16)

                # Начальный угол
                start_raw = parse_angle_value(parts[4])

                # Конечный угол
                stop_raw = parse_angle_value(parts[5])

                start_deg = start_raw / 100
                stop_deg = stop_raw / 100
                total_deg = (stop_raw - start_raw) / 100

                print(f"\n📊 ТЕКУЩИЙ УГОЛ:")
                print(f"   Разрешение: {resolution_raw / 10000:.4f}°")
                print(f"   Стартовый: {start_deg:.1f}°")
                print(f"   Конечный: {stop_deg:.1f}°")
                print(f"   Общий: {total_deg:.1f}°")

                return {
                    "resolution": resolution_raw / 10000,
                    "start": start_deg,
                    "stop": stop_deg,
                    "total": total_deg
                }
            except Exception as e:
                print(f"   ❌ Ошибка парсинга: {e}")
                print(f"   parts: {parts}")

    return None

def set_angle(sock, start_deg, stop_deg):
    """
    Установка угла сканирования

    Args:
        start_deg: начальный угол (например, -35)
        stop_deg: конечный угол (например, 35)
    """
    # Преобразуем в сотые доли градуса
    start_val = int(start_deg * 100)
    stop_val = int(stop_deg * 100)

    # РАБОЧАЯ КОМАНДА
    cmd = f"sWN LMPoutputRange 1 +5000 {start_val} +{stop_val}"
    print(f"\n📡 Установка угла: {cmd}")

    resp = send_cmd(sock, cmd)
    print(f"   Ответ: {resp}")

    if resp and "sWA" in resp:
        print(f"   ✅ Успешно!")
        return True
    else:
        print(f"   ❌ Ошибка!")
        return False

def main():
    print("\n" + "="*70)
    print("🔧 НАСТРОЙКА УГЛА СКАНИРОВАНИЯ")
    print("="*70)

    # Подключаемся
    print("\n🔌 Подключение...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    sock.connect((LIDAR_HOST, LIDAR_PORT))
    print(f"✅ Подключен к {LIDAR_HOST}:{LIDAR_PORT}")

    # Авторизация
    print("\n📡 Авторизация...")
    resp = send_cmd(sock, "sMN SetAccessMode 3 F4724744")
    print(f"   Ответ: {resp}")
    time.sleep(0.2)

    # Показываем текущий угол
    print("\n📊 ТЕКУЩИЙ УГОЛ:")
    get_current_angle(sock)

    # Выбор угла
    print("\n" + "-"*70)
    print("  1 - 20° (-10°…+10°)")
    print("  2 - 30° (-15°…+15°)")
    print("  3 - 40° (-20°…+20°)")
    print("  4 - 50° (-25°…+25°)  ⭐ РЕКОМЕНДУЕТСЯ")
    print("  5 - 60° (-30°…+30°)")
    print("  6 - 70° (-35°…+35°)")
    print("  0 - Выход")
    print("-"*70)

    choice = input("\nВыберите: ").strip()

    angle_configs = {
        "1": (-10, 10, "20° (-10°…+10°)"),
        "2": (-15, 15, "30° (-15°…+15°)"),
        "3": (-20, 20, "40° (-20°…+20°)"),
        "4": (-25, 25, "50° (-25°…+25°)"),
        "5": (-30, 30, "60° (-30°…+30°)"),
        "6": (-35, 35, "70° (-35°…+35°)"),
    }

    if choice == "0":
        print("До свидания!")
        sock.close()
        return

    if choice not in angle_configs:
        print("❌ Неверный выбор")
        sock.close()
        return

    start_deg, stop_deg, name = angle_configs[choice]
    print(f"\n📡 Установка {name}...")

    # Устанавливаем угол
    if set_angle(sock, start_deg, stop_deg):
        time.sleep(0.3)
        # Запускаем сканирование
        print("\n📡 Запуск сканирования...")
        resp = send_cmd(sock, "sMN Run")
        print(f"   Ответ: {resp}")
        time.sleep(0.3)

        # Показываем результат
        print("\n📊 НОВЫЙ УГОЛ:")
        get_current_angle(sock)
    else:
        print("\n❌ Не удалось установить угол!")

    sock.close()
    print("\n🔌 Отключено")

if __name__ == "__main__":
    main()