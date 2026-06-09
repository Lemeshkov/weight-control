# backend/test_angle.py
import socket
import time

def hex_to_signed_int(hex_str):
    """Преобразует HEX строку в знаковое целое"""
    try:
        val = int(hex_str, 16)
        # Если это 32-битное число и старший бит = 1, то оно отрицательное
        if val > 0x7FFFFFFF:
            val = val - 0x100000000
        return val
    except:
        return None

def test_angle():
    host = "192.168.1.101"
    port = 2111
    
    print(f"Подключение к {host}:{port}")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    sock.connect((host, port))
    print("✅ Сокет подключен\n")
    
    def send(cmd, wait=0.5):
        full = f"\x02{cmd}\x03"
        sock.send(full.encode())
        time.sleep(wait)
        resp = sock.recv(65535)
        decoded = resp.decode('utf-8', errors='ignore').strip('\x02\x03')
        return decoded
    
    # 1. Авторизация
    print("1. Авторизация...")
    resp = send("sMN SetAccessMode 3 F4724744")
    print(f"   Ответ: {resp}\n")
    
    # 2. Проверка текущего угла
    print("2. Проверка текущего угла сканирования...")
    resp = send("sRN LMPoutputRange")
    print(f"   Ответ: {resp}")
    
    # Парсим ответ sRA LMPoutputRange 1 1388 FFFF3CB0 1C3A90
    if resp and "sRA LMPoutputRange" in resp:
        parts = resp.split()
        print(f"   Части: {parts}")
        
        if len(parts) >= 5:
            # Разбор параметров
            resolution_hex = parts[2]  # 1388
            start_angle_hex = parts[3]  # FFFF3CB0
            stop_angle_hex = parts[4]   # 1C3A90
            
            resolution = int(resolution_hex, 16)
            start_angle_raw = hex_to_signed_int(start_angle_hex)
            stop_angle_raw = hex_to_signed_int(stop_angle_hex)
            
            print(f"\n   📐 РАСШИФРОВКА:")
            print(f"      Разрешение (сырое): {resolution_hex} = {resolution}")
            print(f"      Разрешение: {resolution / 10000:.4f}°")
            print(f"      Начальный угол (сырой): {start_angle_hex} = {start_angle_raw}")
            print(f"      Начальный угол: {start_angle_raw / 100:.2f}°")
            print(f"      Конечный угол (сырой): {stop_angle_hex} = {stop_angle_raw}")
            print(f"      Конечный угол: {stop_angle_raw / 100:.2f}°")
            print(f"      Общий угол: {(stop_angle_raw - start_angle_raw) / 100:.2f}°")
            
            if start_angle_raw == -3500 and stop_angle_raw == 3500:
                print(f"\n   ✅ Угол настроен правильно!")
            else:
                print(f"\n   ⚠️ Угол не соответствует требуемому (-35°...+35°)")
                print(f"      Текущий: {start_angle_raw/100:.0f}° до {stop_angle_raw/100:.0f}°")
    
    # 3. Попробуем настроить угол
    print("\n3. Настройка угла -35°...+35°...")
    # Отправляем команду в HEX формате
    # sWN LMPoutputRange 1 +5000 -3500 +3500
    resp = send("sWN LMPoutputRange 1 1388 FFFF3CB0 1C3A90")
    print(f"   Ответ: {resp}")
    
    # 4. Применяем настройки
    print("\n4. Применение настроек...")
    resp = send("sMN Logout")
    print(f"   Logout: {resp}")
    resp = send("sMN SetAccessMode 3 F4724744")
    print(f"   Login: {resp}")
    resp = send("sMN Run")
    print(f"   Run: {resp}")
    
    # 5. Проверяем снова
    print("\n5. Проверка после настройки...")
    resp = send("sRN LMPoutputRange")
    print(f"   Ответ: {resp}")
    
    if resp and "sRA LMPoutputRange" in resp:
        parts = resp.split()
        if len(parts) >= 5:
            start_angle_hex = parts[3]
            stop_angle_hex = parts[4]
            start_angle_raw = hex_to_signed_int(start_angle_hex)
            stop_angle_raw = hex_to_signed_int(stop_angle_hex)
            
            print(f"\n   📐 НОВЫЙ УГОЛ:")
            print(f"      Начальный: {start_angle_raw / 100:.2f}°")
            print(f"      Конечный: {stop_angle_raw / 100:.2f}°")
            
            if start_angle_raw == -3500 and stop_angle_raw == 3500:
                print(f"\n   ✅ Угол успешно настроен!")
            else:
                print(f"\n   ❌ Не удалось настроить угол")
    
    sock.close()

if __name__ == "__main__":
    test_angle()