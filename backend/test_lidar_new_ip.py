import socket
import time

HOST = "192.168.1.101"
PORT = 2111

def test():
    print(f"Подключение к {HOST}:{PORT}")
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((HOST, PORT))
        print("✅ Сокет подключен")
        
        def send_cmd(cmd, wait=0.5):
            full = f"\x02{cmd}\x03"
            print(f"\n→ {cmd}")
            sock.send(full.encode())
            time.sleep(wait)
            try:
                resp = sock.recv(4096)
                decoded = resp.decode(errors='ignore').strip('\x02\x03')
                print(f"← {decoded[:200]}")
                return decoded
            except socket.timeout:
                print("← ТАЙМАУТ!")
                return None
        
        # 1. Простая команда для проверки связи
        resp = send_cmd("sRN SCdevicestate", wait=1)
        
        # 2. Авторизация
        resp = send_cmd("sMN SetAccessMode 3 F4724744", wait=1)
        
        # 3. Запуск измерений
        resp = send_cmd("sMN Run", wait=1)
        
        # 4. Запрос данных
        print("\n" + "="*50)
        print("ЗАПРОС ДАННЫХ")
        print("="*50)
        resp = send_cmd("sRN LMDscandata", wait=2)
        
        if resp and "sRA LMDscandata" in resp:
            print("\n✅ УСПЕХ! Данные получены")
        else:
            print("\n❌ Данные не получены")
            
            # Пробуем альтернативные команды
            print("\nПробуем альтернативные команды...")
            send_cmd("sRN LMDscandata", wait=2)
            send_cmd("sRN LMDscandata 1", wait=2)
            
        sock.close()
        
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    test()