import telnetlib
import time

HOST = "192.168.0.1"
PORT = 2111
TIMEOUT = 5

def test_lidar_via_telnet():
    print(f"Подключение к {HOST}:{PORT}...")
    
    try:
        # Подключаемся через telnetlib
        tn = telnetlib.Telnet(HOST, PORT, TIMEOUT)
        print("✅ Подключено!")
        
        def send_cmd(cmd):
            # Формат для CoLa A: STX (0x02) + команда + ETX (0x03)
            full_cmd = f"\x02{cmd}\x03"
            print(f"\n→ Отправка: {cmd}")
            tn.write(full_cmd.encode('utf-8'))
            time.sleep(0.3)
            
            # Читаем ответ
            try:
                response = tn.read_some().decode('utf-8', errors='ignore')
                if response:
                    print(f"← Ответ: {response[:200]}")
                return response
            except Exception as e:
                print(f"⚠️ Ошибка чтения: {e}")
                return None
        
        # 1. Проверяем, что лидар отвечает на простой запрос
        print("\n--- Шаг 1: Проверка связи ---")
        send_cmd("sRN SCdevicestate")
        
        # 2. Авторизация (пароль по умолчанию для LMS511)
        print("\n--- Шаг 2: Авторизация ---")
        resp = send_cmd("sMN SetAccessMode 3 F4724744")
        
        # 3. Запуск измерений
        print("\n--- Шаг 3: Запуск измерений ---")
        send_cmd("sMN Run")
        
        # 4. Запрос скана (ОДИН раз - режим Poll)
        print("\n--- Шаг 4: Запрос данных сканирования ---")
        resp = send_cmd("sRN LMDscandata")
        
        # Проверяем, есть ли данные
        if resp and "sRA LMDscandata" in resp:
            print("\n" + "="*50)
            print("✅ УСПЕХ! Лидар вернул данные!")
            print("="*50)
            
            # Показываем структуру данных (первые символы)
            if "DIST1" in resp:
                print("Найдены данные расстояний (DIST1)")
                # Попробуем извлечь несколько первых расстояний
                parts = resp.split()
                # Ищем DIST1 и берем следующие значения
                for i, part in enumerate(parts):
                    if part == "DIST1" and i+1 < len(parts):
                        print(f"Первые расстояния: {parts[i+1:i+10]}")
                        break
        else:
            print("\n❌ Данные не получены. Ответ:")
            print(resp if resp else "Пустой ответ")
        
        tn.close()
        
    except ConnectionRefusedError:
        print("❌ Ошибка: подключение отклонено. Лидар не слушает порт 2111")
        print("   Проверьте в SOPAS ET: Network → Ethernet → Port = 2111")
    except socket.timeout:
        print("❌ Таймаут: лидар не отвечает")
        print("   Проверьте IP адрес (192.168.0.1) и что лидар включен")
    except Exception as e:
        print(f"❌ Ошибка: {type(e).__name__}: {e}")

if __name__ == "__main__":
    import socket  # для исключений
    test_lidar_via_telnet()