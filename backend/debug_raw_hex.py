# backend/debug_raw_hex.py

"""
Диагностический скрипт для просмотра сырых данных с лидара
Показывает все данные в HEX и DEC форматах
"""
import socket
import time
import binascii

LIDAR_HOST = "192.168.1.101"
LIDAR_PORT = 2111

def send_cmd(sock, cmd, wait=0.3):
    """Отправка команды и получение ответа"""
    full_cmd = f"\x02{cmd}\x03"
    sock.send(full_cmd.encode('utf-8'))
    time.sleep(wait)
    response = sock.recv(65535)
    decoded = response.decode('utf-8', errors='ignore')
    decoded = decoded.strip('\x02\x03')
    return decoded, response

def parse_hex_values(hex_str):
    """Парсит HEX строку в десятичное значение"""
    try:
        val = int(hex_str, 16)
        if val > 0x7FFFFFFF:
            val = val - 0x100000000
        return val
    except:
        return None

print("="*80)
print("🔬 ДИАГНОСТИКА СЫРЫХ ДАННЫХ ЛИДАРА")
print("="*80)

# Подключаемся
print("\n🔌 Подключение...")
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5)
sock.connect((LIDAR_HOST, LIDAR_PORT))
print(f"✅ Подключен к {LIDAR_HOST}:{LIDAR_PORT}")

# 1. Авторизация
print("\n📡 Авторизация...")
resp, _ = send_cmd(sock, "sMN SetAccessMode 3 F4724744")
print(f"   Ответ: {resp}")
time.sleep(0.2)

# 2. Получение данных
print("\n📡 Получение сырых данных...")
raw_data, raw_bytes = send_cmd(sock, "sRN LMDscandata")
print(f"   Получено {len(raw_bytes)} байт")

# 3. Показываем полный сырой ответ
print("\n" + "="*80)
print("📄 ПОЛНЫЙ СЫРОЙ ОТВЕТ (текст):")
print("="*80)
print(raw_data)
print("="*80)

# 4. Показываем в HEX
print("\n📄 ПОЛНЫЙ СЫРОЙ ОТВЕТ (HEX):")
print("="*80)
hex_data = binascii.hexlify(raw_bytes).decode('utf-8')
# Разбиваем по 2 символа для читаемости
hex_parts = [hex_data[i:i+2] for i in range(0, len(hex_data), 2)]
print(' '.join(hex_parts[:200]))  # Первые 200 байт
print("...")
print("="*80)

# 5. Разбираем по частям
print("\n📊 РАЗБОР ПО ЧАСТЯМ (SPLIT):")
print("="*80)
parts = raw_data.split()
for i, part in enumerate(parts):
    print(f"   [{i:2d}] {part}")

# 6. Находим DIST1
print("\n" + "="*80)
print("📊 ПАРСИНГ DIST1 (СЫРЫЕ HEX ЗНАЧЕНИЯ):")
print("="*80)

for i, part in enumerate(parts):
    if part == "DIST1":
        print(f"\n✅ Найден DIST1 на позиции {i}")

        # Пропускаем 4 служебных значения
        j = i + 1
        skip_count = 0
        skipped = []
        while j < len(parts) and skip_count < 4:
            skipped.append(parts[j])
            j += 1
            skip_count += 1

        print(f"\n   📌 СЛУЖЕБНЫЕ ЗНАЧЕНИЯ (пропущены):")
        for idx, val in enumerate(skipped):
            hex_val = val
            dec_val = parse_hex_values(val)
            print(f"      [{idx}] HEX: {hex_val:>10} -> DEC: {dec_val}")

        # Читаем все расстояния
        print(f"\n   📏 РАССТОЯНИЯ (HEX → DEC):")
        print(f"   {'№':>4} {'HEX':>12} {'DEC':>10} {'Статус':>15}")
        print(f"   {'-'*4} {'-'*12} {'-'*10} {'-'*15}")

        count = 0
        distances_hex = []
        distances_dec = []

        while j < len(parts) and parts[j] not in ["RSSI1", "RSSI2", "DIST2", "DEVICE"]:
            hex_val = parts[j].strip()
            dec_val = parse_hex_values(hex_val)

            if dec_val is not None:
                distances_hex.append(hex_val)
                distances_dec.append(dec_val)
                count += 1

                # Определяем статус значения
                if dec_val == 0:
                    status = "❌ НУЛЬ"
                elif dec_val < 100:
                    status = "⚠️ ШУМ"
                elif 100 <= dec_val <= 1000:
                    status = "🔵 МУСОР"
                elif 1000 < dec_val <= 2742:
                    status = "🟢 ОБЪЕКТ"
                elif 2742 < dec_val <= 2792:
                    status = "🟡 ПОЛ"
                elif dec_val > 2792:
                    status = "🔴 ДАЛЕКО"
                else:
                    status = "❓ НЕИЗВЕСТНО"

                print(f"   {count:>4} {hex_val:>12} {dec_val:>10} {status}")
            else:
                print(f"   {count+1:>4} {hex_val:>12} {'ОШИБКА':>10}")

            j += 1

        break

# 7. СТАТИСТИКА
print("\n" + "="*80)
print("📊 СТАТИСТИКА:")
print("="*80)

if distances_dec:
    print(f"\n   Всего точек: {len(distances_dec)}")

    # Валидные (> 0)
    valid = [d for d in distances_dec if d > 0]
    print(f"   Валидных (>0): {len(valid)}")

    if valid:
        print(f"   Min: {min(valid)} мм")
        print(f"   Max: {max(valid)} мм")
        print(f"   Avg: {sum(valid)/len(valid):.0f} мм")

        # Группировка по диапазонам
        print(f"\n   📊 ГРУППИРОВКА ПО ДИАПАЗОНАМ:")
        ranges = {
            "0-100 (шум)": [d for d in valid if 0 < d <= 100],
            "100-1000 (мусор)": [d for d in valid if 100 < d <= 1000],
            "1000-2000 (объект)": [d for d in valid if 1000 < d <= 2000],
            "2000-2742 (объект)": [d for d in valid if 2000 < d <= 2742],
            "2742-2792 (пол)": [d for d in valid if 2742 < d <= 2792],
            "2792-3000 (далеко)": [d for d in valid if 2792 < d <= 3000],
        }

        for name, points in ranges.items():
            if points:
                print(f"      {name}: {len(points)} точек")
                if len(points) <= 10:
                    print(f"         Значения: {sorted(points)}")

        # Показываем все уникальные значения
        unique = sorted(set(valid))
        print(f"\n   📊 УНИКАЛЬНЫЕ ЗНАЧЕНИЯ:")
        print(f"      {unique}")

        # Определяем, где находится объект
        print(f"\n   🎯 РЕКОМЕНДАЦИИ:")

        # Ищем объект (1000-2742 мм)
        object_points = [d for d in valid if 1000 < d <= 2742]
        if object_points:
            print(f"      ✅ ОБЪЕКТ НАЙДЕН в диапазоне 1000-2742 мм")
            print(f"         Точек: {len(object_points)}")
            print(f"         Min: {min(object_points)} мм")
            print(f"         Max: {max(object_points)} мм")
            print(f"         Значения: {sorted(set(object_points))}")
        else:
            print(f"      ❌ ОБЪЕКТ НЕ НАЙДЕН в диапазоне 1000-2742 мм")

        # Ищем пол (2742-2792 мм)
        floor_points = [d for d in valid if 2742 < d <= 2792]
        if floor_points:
            print(f"      🏗️ ПОЛ НАЙДЕН в диапазоне 2742-2792 мм")
            print(f"         Точек: {len(floor_points)}")
            print(f"         Значения: {sorted(set(floor_points))}")
        else:
            print(f"      ⚠️ ПОЛ НЕ НАЙДЕН в диапазоне 2742-2792 мм")

    else:
        print("   ❌ Нет валидных расстояний (>0)")
else:
    print("   ❌ Нет данных")

# 8. Проверка угла
print("\n" + "="*80)
print("📊 ПРОВЕРКА УГЛА:")
print("="*80)

resp, _ = send_cmd(sock, "sRN LMPoutputRange")
print(f"   Ответ: {resp}")

if resp and "LMPoutputRange" in resp:
    parts = resp.split()
    if len(parts) >= 6:
        resolution_raw = int(parts[3], 16)
        start_raw = parse_hex_values(parts[4])
        stop_raw = parse_hex_values(parts[5])

        print(f"\n   Разрешение: {resolution_raw / 10000:.4f}°")
        print(f"   Стартовый: {start_raw / 100:.1f}°")
        print(f"   Конечный: {stop_raw / 100:.1f}°")
        print(f"   Общий: {(stop_raw - start_raw) / 100:.1f}°")

sock.close()
print("\n🔌 Отключено")