# backend/test_commands.py
import socket
import time

def send_cmd(sock, cmd):
    full = f"\x02{cmd}\x03"
    sock.send(full.encode('utf-8'))
    time.sleep(0.2)
    try:
        return sock.recv(65535).decode('utf-8', errors='ignore').strip('\x02\x03')
    except:
        return None

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5)
sock.connect(("192.168.1.101", 2111))
print("✅ Подключен")

# Пробуем разные варианты
commands = [
    "sMN SetAccessMode 3 F4724744",
    "sWN LMPoutputRange 1 5000 FFFF3CB0 0DAC",
    "sWN LMPoutputRange 1 +5000 FFFF3CB0 +0DAC",
    "sWN LMPoutputRange 1 5000 -3500 3500",
    "sWN LMPoutputRange 1 +5000 -3500 +3500",
    "sMN Run",
]

for cmd in commands:
    print(f"\n📡 {cmd}")
    resp = send_cmd(sock, cmd)
    print(f"   Ответ: {resp[:100] if resp else 'None'}")

sock.close()