# backend/test_angle_v2.py
import socket
import time

def hex_to_signed_32bit(hex_str):
    """Преобразует 32-битное HEX в знаковое целое"""
    val = int(hex_str, 16)
    if val > 0x7FFFFFFF:
        val = val - 0x100000000
    return val

def test_angle():
    host = "192.168.1.101"
    port = 2111
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    sock.connect((host, port))
    print("✅ Подключен\n")
    
    def send(cmd, wait=0.3):
        full = f"\x02{cmd}\x03"
        sock.send(full.encode())
        time.sleep(wait)
        resp = sock.recv(65535)
        decoded = resp.decode('utf-8', errors='ignore').strip('\x02\x03')
        print(f"→ {cmd}")
        print(f"← {decoded}")
        return decoded
    
    # Авторизация
    send("sMN SetAccessMode 3 F4724744")
    
    # Отправляем команду в правильном формате
    print("\n--- Отправка команды ---")
    send("sWN LMPoutputRange 1 5000 -3500 3500")
    
    # Применяем
    print("\n--- Применение ---")
    send("sMN Logout")
    send("sMN SetAccessMode 3 F4724744")
    send("sMN Run")
    
    # Проверяем
    print("\n--- Проверка ---")
    resp = send("sRN LMPoutputRange")
    
    # Парсим ответ
    if "sRA LMPoutputRange" in resp:
        parts = resp.split()
        if len(parts) >= 5:
            resolution = int(parts[2], 16)
            start_hex = parts[3]
            stop_hex = parts[4]
            
            start_val = hex_to_signed_32bit(start_hex)
            stop_val = int(stop_hex, 16)
            
            print(f"\n📐 РАСШИФРОВКА:")
            print(f"  Разрешение: {resolution} ({resolution/10000:.4f}°)")
            print(f"  Начальный угол: {start_hex} = {start_val} ({start_val/100:.2f}°)")
            print(f"  Конечный угол: {stop_hex} = {stop_val} ({stop_val/100:.2f}°)")
            print(f"  Общий угол: {(stop_val - start_val)/100:.2f}°")
    
    sock.close()

if __name__ == "__main__":
    test_angle()