# backend/configure_lidar.py
"""
Скрипт для правильной настройки лидара SICK LMS511
"""
import socket
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def send_command(sock, cmd):
    """Отправить команду и получить ответ"""
    full_cmd = f"\x02{cmd}\x03"
    sock.send(full_cmd.encode('utf-8'))
    time.sleep(0.2)
    response = sock.recv(65535)
    decoded = response.decode('utf-8', errors='ignore')
    decoded = decoded.strip('\x02\x03')
    return decoded

def configure_lidar():
    """Настройка лидара для правильного сканирования"""
    host = "192.168.1.101"
    port = 2111
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        logger.info(f"✅ Подключен к {host}:{port}")
        
        # 1. Выход из текущего режима
        logger.info("1. Выход из текущего режима...")
        response = send_command(sock, "sMN Logout")
        logger.info(f"   Ответ: {response}")
        time.sleep(0.5)
        
        # 2. Вход в режим администрирования
        logger.info("2. Вход в режим администрирования...")
        response = send_command(sock, "sMN SetAccessMode 3 F4724744")
        logger.info(f"   Ответ: {response}")
        time.sleep(0.5)
        
        # 3. НАСТРОЙКА УГЛА СКАНИРОВАНИЯ (от -35° до +35°)
        logger.info("3. Настройка угла сканирования (-35° до +35°)...")
        response = send_command(sock, "sWN LMPoutputRange 1 5000 -3500 3500")
        logger.info(f"   Ответ: {response}")
        time.sleep(0.5)
        
        # 4. НАСТРОЙКА ДИАПАЗОНА РАССТОЯНИЙ (фильтруем дальние)
        logger.info("4. Настройка диапазона расстояний (фильтр 100-3000 мм)...")
        # Устанавливаем минимальное и максимальное расстояние
        response = send_command(sock, "sWN LMPminMax 1 100 3000")
        logger.info(f"   Ответ: {response}")
        time.sleep(0.5)
        
        # 5. НАСТРОЙКА ФИЛЬТРА ШУМА
        logger.info("5. Настройка фильтра шума...")
        # Включаем медианный фильтр
        response = send_command(sock, "sWN LMPmedianFilter 1 1")
        logger.info(f"   Ответ: {response}")
        time.sleep(0.5)
        
        # 6. ПРОВЕРКА ТЕКУЩИХ НАСТРОЕК
        logger.info("\n6. Проверка текущих настроек...")
        
        # Проверяем угол
        response = send_command(sock, "sRN LMPoutputRange")
        logger.info(f"   Угол: {response}")
        
        # Проверяем диапазон
        response = send_command(sock, "sRN LMPminMax")
        logger.info(f"   Диапазон: {response}")
        
        # 7. Запуск сканирования
        logger.info("7. Запуск сканирования...")
        response = send_command(sock, "sMN Run")
        logger.info(f"   Ответ: {response}")
        time.sleep(0.5)
        
        # 8. Тестовое сканирование
        logger.info("\n8. Тестовое сканирование...")
        response = send_command(sock, "sRN LMDscandata")
        
        # Проверяем, что данные изменились
        if "DIST1" in response:
            logger.info("   ✅ Данные получены, есть DIST1")
            # Парсим первые несколько точек
            parts = response.split()
            distances = []
            found_dist = False
            for i, part in enumerate(parts):
                if part == "DIST1" and i + 1 < len(parts):
                    j = i + 1
                    count = 0
                    while j < len(parts) and parts[j] not in ["RSSI1", "RSSI2", "DIST2", "DEVICE"] and count < 10:
                        try:
                            val = int(parts[j], 16)
                            if val > 0x7FFFFFFF:
                                val = val - 0x100000000
                            distances.append(val)
                        except:
                            pass
                        j += 1
                        count += 1
                    found_dist = True
                    break
            
            if distances:
                logger.info(f"   Первые 10 точек: {distances}")
                if all(d < 3000 for d in distances):
                    logger.info("   ✅ Точки в пределах 3000 мм (хорошо)")
                else:
                    logger.info(f"   ⚠️ Есть точки > 3000 мм: {[d for d in distances if d > 3000]}")
        else:
            logger.warning("   ❌ DIST1 не найден в ответе")
        
        sock.close()
        logger.info("\n✅ Настройка завершена!")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return False

def check_current_settings():
    """Проверка текущих настроек лидара"""
    host = "192.168.1.101"
    port = 2111
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        logger.info(f"✅ Подключен к {host}:{port}")
        
        # Проверяем настройки
        commands = [
            "sRN LMPoutputRange",  # Угол
            "sRN LMPminMax",       # Диапазон
            "sRN LMPmedianFilter", # Фильтр
            "sRN LMPscaningFrequency", # Частота
        ]
        
        logger.info("\n📊 ТЕКУЩИЕ НАСТРОЙКИ ЛИДАРА:")
        for cmd in commands:
            response = send_command(sock, cmd)
            logger.info(f"  {cmd}: {response}")
        
        sock.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return False

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🔧 НАСТРОЙКА ЛИДАРА SICK LMS511")
    print("="*60)
    
    print("\n1. Проверка текущих настроек...")
    check_current_settings()
    
    print("\n2. Настройка лидара...")
    configure_lidar()
    
    print("\n3. Проверка настроек после изменения...")
    check_current_settings()
    
    print("\n" + "="*60)
    print("✅ Готово! Теперь можно запускать основное приложение.")
    print("="*60)