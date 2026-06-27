# backend/set_angle.py
"""
Простой скрипт для настройки угла сканирования лидара
"""
import socket
import time

LIDAR_HOST = "192.168.1.101"
LIDAR_PORT = 2111

def send_cmd(sock, cmd):
    """Отправка команды и получение ответа"""
    full_cmd = f"\x02{cmd}\x03"
    try:
        sock.send(full_cmd.encode('utf-8'))
        time.sleep(0.2)
        response = sock.recv(65535)
        decoded = response.decode('utf-8', errors='ignore')
        decoded = decoded.strip('\x02\x03')
        return decoded
    except socket.timeout:
        print(f"❌ Таймаут при отправке {cmd}")
        return None
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None

def set_angle_70():
    """Установить угол 70° (-35°…+35°)"""
    print("="*70)
    print("🔧 НАСТРОЙКА УГЛА СКАНИРОВАНИЯ 70° (-35°…+35°)")
    print("="*70)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((LIDAR_HOST, LIDAR_PORT))
        print(f"✅ Подключен к {LIDAR_HOST}:{LIDAR_PORT}")

        # 1. Выход
        print("\n📡 1. Выход из режима...")
        resp = send_cmd(sock, "sMN Logout")
        print(f"   Ответ: {resp if resp else 'None'}")
        time.sleep(0.2)

        # 2. Авторизация
        print("\n📡 2. Авторизация...")
        resp = send_cmd(sock, "sMN SetAccessMode 3 F4724744")
        print(f"   Ответ: {resp if resp else 'None'}")
        time.sleep(0.2)

        # 3. Установка угла 70°
        print("\n📡 3. Установка угла 70° (-35°…+35°)...")

        # ⭐ РАБОЧАЯ КОМАНДА
        cmd = "sWN LMPoutputRange 1 +5000 -1000 +1000"
        print(f"   Отправка: {cmd}")
        resp = send_cmd(sock, cmd)
        print(f"   Ответ: {resp if resp else 'None'}")
        time.sleep(0.2)

        # 4. Запуск
        print("\n📡 4. Запуск сканирования...")
        resp = send_cmd(sock, "sMN Run")
        print(f"   Ответ: {resp if resp else 'None'}")
        time.sleep(0.2)

        # 5. Проверка
        print("\n📡 5. Проверка угла...")
        resp = send_cmd(sock, "sRN LMPoutputRange")
        print(f"   Ответ: {resp if resp else 'None'}")

        if resp and "LMPoutputRange" in resp:
            parts = resp.split()
            print(f"\n📊 РЕЗУЛЬТАТ:")
            print(f"   Разрешение: {parts[2]}")
            print(f"   Начальный угол: {parts[3]} -> {int(parts[3]) / 100}°")
            print(f"   Конечный угол: {parts[4]} -> {int(parts[4]) / 100}°")
            print(f"   Итого: {int(parts[4]) / 100 - int(parts[3]) / 100}°")

        sock.close()
        print("\n🔌 Отключено")

    except Exception as e:
        print(f"❌ Ошибка: {e}")

def set_angle_20():
    """Установить угол 20° (-10°…+10°)"""
    print("="*70)
    print("🔧 НАСТРОЙКА УГЛА СКАНИРОВАНИЯ 20° (-10°…+10°)")
    print("="*70)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((LIDAR_HOST, LIDAR_PORT))
        print(f"✅ Подключен к {LIDAR_HOST}:{LIDAR_PORT}")

        send_cmd(sock, "sMN Logout")
        time.sleep(0.2)
        send_cmd(sock, "sMN SetAccessMode 3 F4724744")
        time.sleep(0.2)

        print("\n📡 Установка угла 20° (-10°…+10°)...")
        cmd = "sWN LMPoutputRange 1 +5000 -1000 +1000"
        print(f"   Отправка: {cmd}")
        resp = send_cmd(sock, cmd)
        print(f"   Ответ: {resp if resp else 'None'}")
        time.sleep(0.2)

        send_cmd(sock, "sMN Run")
        time.sleep(0.2)

        resp = send_cmd(sock, "sRN LMPoutputRange")
        print(f"\n📡 Проверка: {resp if resp else 'None'}")

        sock.close()
        print("\n🔌 Отключено")

    except Exception as e:
        print(f"❌ Ошибка: {e}")

def main():
    print("\n" + "="*70)
    print("🔧 НАСТРОЙКА УГЛА СКАНИРОВАНИЯ")
    print("="*70)
    print("  1 - Установить 70° (-35°…+35°)")
    print("  2 - Установить 20° (-10°…+10°)")
    print("  3 - Показать текущий угол")
    print("  0 - Выход")

    choice = input("\nВыберите: ").strip()

    if choice == "1":
        set_angle_70()
    elif choice == "2":
        set_angle_20()
    elif choice == "3":
        # Показываем текущий угол
        print("\n📡 Проверка текущего угла...")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((LIDAR_HOST, LIDAR_PORT))
            resp = send_cmd(sock, "sRN LMPoutputRange")
            print(f"   Ответ: {resp if resp else 'None'}")
            sock.close()
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    elif choice == "0":
        print("До свидания!")
    else:
        print("Неверный выбор")

if __name__ == "__main__":
    main()