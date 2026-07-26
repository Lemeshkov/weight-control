# backend/raw_data_dump.py
"""
Получение ВСЕХ сырых данных с лидара
Использует непрерывный режим для получения полного набора данных
"""
import socket
import time

HOST = "192.168.1.101"
PORT = 2111


def send(sock, cmd):
    print(f"\n>>> {cmd}")

    telegram = f"\x02{cmd}\x03"

    sock.sendall(telegram.encode())

    data = b""

    while True:
        part = sock.recv(4096)

        if not part:
            break

        data += part

        # конец telegram
        if b"\x03" in part:
            break

    text = data.decode(errors="ignore").strip("\x02\x03")

    print(f"Получено {len(text)} символов")

    return text


sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(10)

print("Подключение...")

sock.connect((HOST, PORT))

print("OK")

# Авторизация
print(send(sock, "sMN SetAccessMode 3 F4724744"))
time.sleep(0.2)

print(send(sock, "sMN Run"))
time.sleep(0.2)

# Получаем полный telegram
raw = send(sock, "sRN LMDscandata")

print("\n===================== ПОЛНЫЙ TELEGRAM =====================\n")
print(raw)
print("\n===========================================================\n")

with open("lmdscandata_full.txt", "w", encoding="utf8") as f:
    f.write(raw)

print("Полный ответ сохранён в lmdscandata_full.txt")

parts = raw.split()

print("\nКоличество частей:", len(parts))

print("\n===================== ВСЕ ПОЛЯ =====================")

for i, p in enumerate(parts):
    print(f"[{i:03}] {p}")

print("===================================================")

if "DIST1" in parts:

    idx = parts.index("DIST1")

    print("\nDIST1 найден на позиции", idx)

    for i in range(idx, min(idx + 30, len(parts))):
        print(f"[{i}] {parts[i]}")

    if idx + 5 < len(parts):

        try:
            count = int(parts[idx + 5], 16)

            print("\nКоличество точек (NumberOfData):", count)

        except Exception as e:
            print(e)

sock.close()