# backend/debug_lidar_raw_hex.py
"""
Скрипт для отладки сырых данных лидара
Показывает HEX-значения и их декодирование
"""
import socket
import time
import binascii

# ═══════════════════════════════════════════════════════════
# НАСТРОЙКИ
# ═══════════════════════════════════════════════════════════
LIDAR_HOST = "192.168.1.101"
LIDAR_PORT = 2111


def connect_lidar(host=LIDAR_HOST, port=LIDAR_PORT):
    """Подключение к лидару"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        print(f"✅ Подключен к {host}:{port}")
        
        sock.send(b"\x02sMN SetAccessMode 3 F4724744\x03")
        time.sleep(0.2)
        sock.send(b"\x02sMN Run\x03")
        time.sleep(0.2)
        
        return sock
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return None


def get_scan_data(sock):
    """Получение данных сканирования"""
    try:
        sock.send(b"\x02sRN LMDscandata\x03")
        time.sleep(0.3)
        response = sock.recv(65535)
        decoded = response.decode('utf-8', errors='ignore')
        decoded = decoded.strip('\x02\x03')
        return decoded, response
    except Exception as e:
        print(f"❌ Ошибка получения данных: {e}")
        return None, None


def hex_to_int(hex_str):
    """Преобразует HEX строку в целое число"""
    try:
        value = int(hex_str, 16)
        if value > 0x7FFFFFFF:
            value = value - 0x100000000
        return value
    except ValueError:
        return None


def parse_distances_correct(raw_data):
    """
    ПРАВИЛЬНЫЙ парсинг расстояний из DIST1
    Пропускает первые 4 служебных значения
    """
    if not raw_data:
        return []
    
    parts = raw_data.split()
    distances = []
    all_values = []  # Для отладки
    
    for i, part in enumerate(parts):
        if part == "DIST1" and i + 1 < len(parts):
            j = i + 1
            
            # ═══════════════════════════════════════════════════════════
            # 1. Собираем ВСЕ значения (для отладки)
            # ═══════════════════════════════════════════════════════════
            temp_j = j
            while temp_j < len(parts) and parts[temp_j] not in ["RSSI1", "RSSI2", "DIST2", "DEVICE"]:
                hex_val = parts[temp_j].strip()
                if hex_val:
                    dec_val = hex_to_int(hex_val)
                    all_values.append({
                        "hex": hex_val,
                        "dec": dec_val,
                        "index": temp_j - j
                    })
                temp_j += 1
            
            # ═══════════════════════════════════════════════════════════
            # 2. ПРОПУСКАЕМ ПЕРВЫЕ 4 СЛУЖЕБНЫХ ЗНАЧЕНИЯ
            # ═══════════════════════════════════════════════════════════
            skip_count = 0
            while j < len(parts) and skip_count < 4:
                j += 1
                skip_count += 1
            
            # ═══════════════════════════════════════════════════════════
            # 3. ПАРСИМ РЕАЛЬНЫЕ РАССТОЯНИЯ
            # ═══════════════════════════════════════════════════════════
            while j < len(parts) and parts[j] not in ["RSSI1", "RSSI2", "DIST2", "DEVICE"]:
                try:
                    hex_val = parts[j].strip()
                    if hex_val:
                        value = int(hex_val, 16)
                        if value > 0x7FFFFFFF:
                            value = value - 0x100000000
                        if 100 < value < 5000:
                            distances.append(value)
                except ValueError:
                    pass
                j += 1
            break
    
    return distances, all_values


def debug_scan():
    """Отладка сканирования"""
    print("\n" + "="*70)
    print("🔬 ОТЛАДКА СЫРЫХ ДАННЫХ ЛИДАРА (С ИСПРАВЛЕННЫМ ПАРСИНГОМ)")
    print("="*70)
    
    sock = connect_lidar()
    if not sock:
        return
    
    try:
        raw_text, raw_bytes = get_scan_data(sock)
        
        if not raw_text:
            print("❌ Нет данных")
            return
        
        print(f"✅ Получено {len(raw_bytes)} байт")
        
        # ═══════════════════════════════════════════════════════════
        # ПАРСИМ С ПРОПУСКОМ СЛУЖЕБНЫХ ЗНАЧЕНИЙ
        # ═══════════════════════════════════════════════════════════
        distances, all_values = parse_distances_correct(raw_text)
        
        print(f"\n📊 РЕЗУЛЬТАТЫ ПАРСИНГА:")
        print(f"  Всего значений в DIST1: {len(all_values)}")
        print(f"  Служебных значений (пропущено): 4")
        print(f"  Реальных расстояний: {len(distances)}")
        
        # ═══════════════════════════════════════════════════════════
        # ПОКАЗЫВАЕМ ПЕРВЫЕ 10 СЛУЖЕБНЫХ ЗНАЧЕНИЙ
        # ═══════════════════════════════════════════════════════════
        print("\n" + "="*70)
        print("📋 ПЕРВЫЕ 10 ЗНАЧЕНИЙ DIST1 (включая служебные)")
        print("="*70)
        for i, val in enumerate(all_values[:14]):
            if i < 4:
                print(f"  #{i+1}: HEX={val['hex']} → DEC={val['dec']} мм ⚠️ СЛУЖЕБНОЕ (пропущено)")
            else:
                print(f"  #{i+1}: HEX={val['hex']} → DEC={val['dec']} мм ✅ РАССТОЯНИЕ")
        
        # ═══════════════════════════════════════════════════════════
        # СТАТИСТИКА РЕАЛЬНЫХ РАССТОЯНИЙ
        # ═══════════════════════════════════════════════════════════
        if distances:
            print("\n" + "="*70)
            print("📊 СТАТИСТИКА РЕАЛЬНЫХ РАССТОЯНИЙ")
            print("="*70)
            print(f"  Всего точек: {len(distances)}")
            print(f"  МИНИМАЛЬНОЕ: {min(distances)} мм")
            print(f"  МАКСИМАЛЬНОЕ: {max(distances)} мм")
            print(f"  СРЕДНЕЕ: {sum(distances) / len(distances):.1f} мм")
            
            # ═══════════════════════════════════════════════════════════
            # РАСПРЕДЕЛЕНИЕ ПО ДИАПАЗОНАМ
            # ═══════════════════════════════════════════════════════════
            ranges = {
                "0-100": 0,
                "100-500": 0,
                "500-1000": 0,
                "1000-1500": 0,
                "1500-2000": 0,
                "2000-2500": 0,
                "2500-3000": 0,
                "3000+": 0
            }
            
            for d in distances:
                if d < 100:
                    ranges["0-100"] += 1
                elif d < 500:
                    ranges["100-500"] += 1
                elif d < 1000:
                    ranges["500-1000"] += 1
                elif d < 1500:
                    ranges["1000-1500"] += 1
                elif d < 2000:
                    ranges["1500-2000"] += 1
                elif d < 2500:
                    ranges["2000-2500"] += 1
                elif d < 3000:
                    ranges["2500-3000"] += 1
                else:
                    ranges["3000+"] += 1
            
            print("\n  📊 РАСПРЕДЕЛЕНИЕ ПО ДИАПАЗОНАМ:")
            for key, value in ranges.items():
                if value > 0:
                    print(f"    {key}: {value} точек ({value/len(distances)*100:.1f}%)")
            
            # ═══════════════════════════════════════════════════════════
            # ПЕРВЫЕ 20 РАССТОЯНИЙ
            # ═══════════════════════════════════════════════════════════
            print("\n" + "="*70)
            print("📏 ПЕРВЫЕ 20 РЕАЛЬНЫХ РАССТОЯНИЙ")
            print("="*70)
            for i, d in enumerate(distances[:20]):
                print(f"  #{i+1}: {d} мм")
            
            # ═══════════════════════════════════════════════════════════
            # ПОСЛЕДНИЕ 20 РАССТОЯНИЙ
            # ═══════════════════════════════════════════════════════════
            print("\n" + "="*70)
            print("📏 ПОСЛЕДНИЕ 20 РЕАЛЬНЫХ РАССТОЯНИЙ")
            print("="*70)
            for i, d in enumerate(distances[-20:]):
                print(f"  #{i+1}: {d} мм")
        
        else:
            print("\n❌ Нет реальных расстояний!")
        
    finally:
        sock.close()
        print("\n🔌 Отключено")


def main():
    """Главное меню"""
    print("\n🔬 ОТЛАДКА СЫРЫХ ДАННЫХ ЛИДАРА")
    print("="*70)
    print("  1 - Показать данные с исправленным парсингом")
    print("  0 - Выход")
    
    choice = input("\nВыберите: ").strip()
    
    if choice == "1":
        debug_scan()
    elif choice == "0":
        print("\nДо свидания!")
    else:
        print("\n❌ Неверный выбор")


if __name__ == "__main__":
    main()