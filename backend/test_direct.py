import socket
import time

host = "192.168.1.101"
port = 2111

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(3)
sock.connect((host, port))
print("✅ Подключено")

def send(cmd):
    full = f"\x02{cmd}\x03"
    sock.send(full.encode())
    time.sleep(0.3)
    resp = sock.recv(65535)
    decoded = resp.decode(errors='ignore').strip('\x02\x03')
    print(f"{cmd[:20]} -> {decoded[:100]}")
    return decoded

send("sMN SetAccessMode 3 F4724744")
send("sMN Run")
send("sRN LMDscandata")

sock.close()