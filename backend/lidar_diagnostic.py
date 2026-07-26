# backend/lidar_diagnostic.py
"""
Полный диагностический файл
"""

import socket
import time
from datetime import datetime

HOST = "192.168.1.101"
PORT = 2111
PASSWORD = "F4724744"


class LMSDiagnostic:

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = None

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(5)
        self.sock.connect((self.host, self.port))
        print(f"Подключено к {self.host}:{self.port}")

    def disconnect(self):
        if self.sock:
            self.sock.close()

    def send(self, cmd):

        telegram = f"\x02{cmd}\x03"

        print(f"\n>>> {cmd}")

        self.sock.sendall(telegram.encode())

        data = b""

        while True:

            try:
                part = self.sock.recv(4096)

                if not part:
                    break

                data += part

                if b'\x03' in part:
                    break

            except socket.timeout:
                break

        text = data.decode(errors="ignore").strip("\x02\x03")

        print(f"<<< {len(text)} bytes")

        return text


diag = LMSDiagnostic(HOST, PORT)

diag.connect()

results = []

def run(cmd):

    try:

        ans = diag.send(cmd)

        results.append((cmd, ans))

        time.sleep(0.2)

    except Exception as e:

        results.append((cmd, f"ERROR: {e}"))


print("\nАвторизация...\n")

run(f"sMN SetAccessMode 3 {PASSWORD}")

run("sMN Run")

print("\n=================== DEVICE ===================")

device_commands = [

    "sRN DeviceIdent",
    "sRN SerialNumber",
    "sRN FirmwareVersion",
    "sRN SCdevicestate",
    "sRN DeviceState",
]

for c in device_commands:
    run(c)

print("\n=================== SCAN ===================")

scan_commands = [

    "sRN LMDscandata",

    "sRN LMDscancfg",

    "sRN LMPoutputRange",

    "sRN LMDscandatacfg",

    "sRN ScanDataCfg",

    "sRN ScanDataEnable",

    "sRN FREchoFilter",

    "sRN LFPmeanfilter",

    "sRN LFPangleRangeFilter",

    "sRN LFPparticleFilter",

    "sRN ContaminationResult",

]

for c in scan_commands:
    run(c)

print("\n=================== TEST CONTINUOUS ===================")

run("sEN LMDscandata 1")

print("\nОжидание данных...")

for i in range(5):

    try:

        data = diag.sock.recv(8192)

        if data:

            txt = data.decode(errors="ignore")

            print(f"Packet {i+1}: {len(txt)} bytes")

            results.append((f"STREAM_{i+1}", txt))

    except socket.timeout:
        print("timeout")

    except Exception as e:
        print(e)

run("sEN LMDscandata 0")

diag.disconnect()

filename = f"lidar_diagnostic_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

with open(filename, "w", encoding="utf8") as f:

    for cmd, ans in results:

        f.write("=" * 80 + "\n")

        f.write(cmd + "\n")

        f.write("-" * 80 + "\n")

        f.write(ans + "\n\n")

print("\nДиагностика завершена.")
print("Файл:", filename)