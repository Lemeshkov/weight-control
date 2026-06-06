import socket
import time

HOST = "192.168.0.1"
PORT = 2111

try:
    print(f"Подключение к {HOST}:{PORT}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    sock.connect((HOST, PORT))
    print("✅ Подключено")
    
    # Вход в режим
    sock.send(b'sMN SetAccessMode 3 F4724744\n')
    time.sleep(0.3)
    print("✅ Режим авторизован")
    
    # Запуск измерений
    sock.send(b'sMN Run\n')
    time.sleep(0.5)
    print("✅ Измерения запущены")
    
    # Запрос данных
    sock.send(b'sMN LMDscandata\n')
    print("⏳ Ожидание данных...")
    
    data = sock.recv(65535)
    print(f"✅ Получено {len(data)} байт")
    print(data[:500])
    
    sock.close()
    
except Exception as e:
    print(f"❌ Ошибка: {e}")