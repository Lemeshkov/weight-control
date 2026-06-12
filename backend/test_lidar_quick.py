# backend/test_lidar_quick.py
import socket
import time

def test():
    host = "192.168.1.101"
    port = 2111
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect((host, port))
        print("✅ Подключен")
        
        def send(cmd):
            full = f"\x02{cmd}\x03"
            sock.send(full.encode())
            time.sleep(0.3)
            resp = sock.recv(65535)
            decoded = resp.decode(errors='ignore').strip('\x02\x03')
            print(f"→ {cmd}")
            print(f"← {decoded[:100]}")
            return decoded
        
        send("sMN SetAccessMode 3 F4724744")
        send("sMN Run")
        send("sRN LMDscandata")
        
        sock.close()
        print("\n✅ Лидар работает!")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    test()