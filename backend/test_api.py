# backend/test_api.py
import socket
import time
import json

def test_lidar():
    host = "192.168.1.101"
    port = 2111
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        print("✅ Подключен")
        
        def send(cmd):
            full = f"\x02{cmd}\x03"
            sock.send(full.encode())
            time.sleep(0.3)
            resp = sock.recv(65535)
            decoded = resp.decode('utf-8', errors='ignore').strip('\x02\x03')
            return decoded
        
        # Авторизация
        send("sMN SetAccessMode 3 F4724744")
        
        # Запуск
        send("sMN Run")
        
        # Запрос скана
        response = send("sRN LMDscandata")
        
        print(f"Получено {len(response)} байт")
        print(f"Первые 500 символов:\n{response[:500]}")
        
        sock.close()
        
    except Exception as e:
        print(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_lidar()
    