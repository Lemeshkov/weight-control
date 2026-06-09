# backend/test_angle_fixed.py
import socket
import time

def test_angle_fixed():
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
        print(f"→ {cmd}")
        print(f"← {decoded}\n")
        return decoded
    
    # 1. Авторизация
    print("1. Авторизация...")
    send("sMN SetAccessMode 3 F4724744")
    
    # 2. Пробуем разные форматы команды
    print("2. Пробуем настроить угол (разные форматы)...")
    
    # Формат 1: Десятичные значения
    print("\n--- Формат 1: десятичные ---")
    send("sWN LMPoutputRange 1 5000 -3500 3500")
    
    # Формат 2: С плюсами
    print("\n--- Формат 2: с плюсами ---")
    send("sWN LMPoutputRange 1 +5000 -3500 +3500")
    
    # Формат 3: Без пробелов
    print("\n--- Формат 3: без пробелов ---")
    send("sWN LMPoutputRange 1 5000,-3500,3500")
    
    # 3. Выходим и заходим заново
    print("3. Применение настроек...")
    send("sMN Logout")
    send("sMN SetAccessMode 3 F4724744")
    send("sMN Run")
    
    # 4. Проверяем
    print("4. Проверка угла...")
    send("sRN LMPoutputRange")
    
    sock.close()

if __name__ == "__main__":
    test_angle_fixed()