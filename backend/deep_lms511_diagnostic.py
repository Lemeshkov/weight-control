# backend/deep_lms511_diagnostic.py
"""
имеет смысл сделать не просто тест, а форензик-диагностику. Цель — выяснить, почему SOPAS получает полный поток (~200 точек), а TCP-клиент только три точки.

Я бы проверил сразу всё:

    Версию прошивки.
    Все настройки сканирования.
    Все доступные команды LMD.
    Непрерывный режим.
    Все возможные варианты получения scan data.
    Размер каждого telegram.
    Hex-дамп каждого ответа.
    Проверку CoLa A.
    Проверку нескольких команд, которые отличаются между прошивками LMS5xx
"""
import socket
import time
import datetime
import binascii

HOST = "192.168.1.101"
PORT = 2111
PASSWORD = "F4724744"


class LMS511:

    def __init__(self):
        self.sock = None

    def connect(self):
        print("=" * 80)
        print("CONNECT")
        print("=" * 80)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(5)
        self.sock.connect((HOST, PORT))

        print("CONNECTED")

    def close(self):
        if self.sock:
            self.sock.close()

    def send(self, cmd):

        telegram = b"\x02" + cmd.encode() + b"\x03"

        print()
        print(">" * 40)
        print(cmd)

        self.sock.sendall(telegram)

        data = b""

        while True:

            try:

                part = self.sock.recv(8192)

                if not part:
                    break

                data += part

                if b"\x03" in part:
                    break

            except socket.timeout:
                break

        text = data.decode(errors="ignore").strip("\x02\x03")

        print("Bytes :", len(data))
        print("Chars :", len(text))
        print("Parts :", len(text.split()))

        return data, text


diag = LMS511()

diag.connect()

log = []


def execute(cmd):

    try:

        raw, txt = diag.send(cmd)

        log.append({
            "cmd": cmd,
            "raw": raw,
            "text": txt
        })

    except Exception as e:

        log.append({
            "cmd": cmd,
            "raw": b"",
            "text": "ERROR : " + str(e)
        })

    time.sleep(0.2)


print("\nLOGIN")

execute(f"sMN SetAccessMode 3 {PASSWORD}")

execute("sMN Run")

###############################################################################
print("\nDEVICE")
###############################################################################

device = [

    "sRN DeviceIdent",
    "sRN SerialNumber",
    "sRN FirmwareVersion",
    "sRN SCdevicestate",
    "sRN DeviceState",
    "sRN LocationName",
    "sRN EthernetConfig",
]

for c in device:
    execute(c)

###############################################################################
print("\nSCAN CONFIG")
###############################################################################

scan = [

    "sRN LMDscancfg",
    "sRN LMPoutputRange",
    "sRN LMDscandatacfg",

    "sRN FREchoFilter",

    "sRN LFPmeanfilter",
    "sRN LFPangleRangeFilter",
    "sRN LFPparticleFilter",

    "sRN ScanDataCfg",
    "sRN ScanDataEnable",

    "sRN ContaminationResult",

]

for c in scan:
    execute(c)

###############################################################################
print("\nSCAN TEST")
###############################################################################

scan_cmds = [

    "sRN LMDscandata",

    "sRN LMDscandata",

    "sRN LMDscandata",

]

for c in scan_cmds:
    execute(c)

###############################################################################
print("\nCONTINUOUS")
###############################################################################

execute("sEN LMDscandata 1")

for i in range(10):

    try:

        packet = diag.sock.recv(8192)

        print(f"STREAM {i+1}: {len(packet)} bytes")

        log.append({
            "cmd": f"STREAM {i+1}",
            "raw": packet,
            "text": packet.decode(errors="ignore")
        })

    except socket.timeout:

        print("STREAM TIMEOUT")

        break

execute("sEN LMDscandata 0")

###############################################################################
print("\nUNKNOWN COMMAND TEST")
###############################################################################

tests = [

    "sRN ScanDataCfg",
    "sRN ScanDataEnable",

    "sRN LFErec",

    "sRN ScanFreq",

    "sRN ActiveApplications",

]

for c in tests:
    execute(c)

###############################################################################
print("\nSAVE")
###############################################################################

filename = "deep_lms511_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".txt"

with open(filename, "w", encoding="utf8") as f:

    for item in log:

        f.write("=" * 100 + "\n")
        f.write(item["cmd"] + "\n")
        f.write("=" * 100 + "\n\n")

        f.write("TEXT\n\n")

        f.write(item["text"])

        f.write("\n\n")

        f.write("HEX\n\n")

        if item["raw"]:

            f.write(binascii.hexlify(item["raw"]).decode())

        f.write("\n\n")

        if item["text"]:

            parts = item["text"].split()

            f.write("PARTS : " + str(len(parts)) + "\n\n")

            for i, p in enumerate(parts):

                f.write(f"[{i:03}] {p}\n")

        f.write("\n\n")

diag.close()

print("\nDONE")
print(filename)