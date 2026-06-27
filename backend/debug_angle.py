# backend/debug_angle.py

def set_angle_and_verify():
    """Устанавливает угол и проверяет"""
    sock = connect_lidar()
    if not sock:
        return

    try:
        # Выход
        send_raw_cmd(sock, "sMN Logout")
        time.sleep(0.2)

        # Авторизация
        send_raw_cmd(sock, "sMN SetAccessMode 3 F4724744")
        time.sleep(0.2)

        # ═══════════════════════════════════════════════════════════
        # ⭐ РАБОЧАЯ КОМАНДА (DECIMAL ФОРМАТ)
        # ═══════════════════════════════════════════════════════════
        print("\n📡 Устанавливаем угол 70° (-35°…+35°)...")

        commands = [
            "sWN LMPoutputRange 1 5000 -3500 3500",
            "sWN LMPoutputRange 1 +5000 -3500 +3500",   # ← РАБОТАЕТ!
        ]

        for cmd in commands:
            print(f"   Отправка: {cmd}")
            resp = send_raw_cmd(sock, cmd)
            print(f"   Ответ: {resp[:100] if resp else 'None'}")
            time.sleep(0.2)

        # Запуск
        send_raw_cmd(sock, "sMN Run")
        time.sleep(0.2)

        # Проверка
        print("\n📡 Проверяем установленный угол...")
        resp = send_raw_cmd(sock, "sRN LMPoutputRange")
        print(f"   Ответ: {resp[:300] if resp else 'None'}")

        if resp and "LMPoutputRange" in resp:
            parts = resp.split()
            print(f"\n📊 РАСШИФРОВКА:")
            if len(parts) >= 5:
                print(f"   Разрешение: {parts[2]}")
                print(f"   Начальный угол: {parts[3]} -> {int(parts[3]) / 100}°")
                print(f"   Конечный угол: {parts[4]} -> {int(parts[4]) / 100}°")

    finally:
        sock.close()
        print("\n🔌 Отключено")