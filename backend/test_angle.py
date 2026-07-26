# backend/test_angle.py

import sys
import os
from pathlib import Path

# Добавляем backend в путь
sys.path.insert(0, str(Path(__file__).parent))

from services.lidar_client import lidar_client
import time
import math

def test_angle():
    """
    Тест для проверки текущего угла сканирования лидара.
    Показывает:
    1. Текущий установленный угол
    2. Количество точек в секторе
    3. Распределение точек по углам
    """
    print("\n" + "="*70)
    print("🔬 ТЕСТ УГЛА СКАНИРОВАНИЯ ЛИДАРА")
    print("="*70 + "\n")

    # Подключаемся к лидару
    if not lidar_client.is_connected:
        print("🔌 Подключаемся к лидару...")
        if not lidar_client.connect():
            print("❌ Не удалось подключиться к лидару")
            return
        print("✅ Лидар подключен")

    # Получаем данные
    print("\n📡 Получаем данные сканирования...")
    scan_data = lidar_client.get_scan_data()

    if not scan_data:
        print("❌ Не удалось получить данные")
        return

    # Парсим сырые данные
    print("\n📊 Парсим данные...")
    raw_distances = lidar_client.parse_raw_data(scan_data)

    if not raw_distances:
        print("❌ Нет данных после парсинга")
        return

    print(f"✅ Получено {len(raw_distances)} сырых точек")

    # ═══════════════════════════════════════════════════════════════
    # 1. ТЕКУЩИЙ УГОЛ
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "-"*70)
    print("📊 1. ТЕКУЩИЙ УГОЛ СКАНИРОВАНИЯ")
    print("-"*70)

    angle_info = lidar_client.get_current_angle_range()

    if angle_info:
        print(f"\n   Текущий угол (из лидара):")
        print(f"      Стартовый угол: {angle_info.get('start_angle_deg', 0):.1f}°")
        print(f"      Конечный угол: {angle_info.get('stop_angle_deg', 0):.1f}°")
        print(f"      Общий угол: {angle_info.get('total_angle_deg', 0):.1f}°")
        print(f"      Разрешение: {angle_info.get('resolution_deg', 0):.4f}°")
    else:
        print("   ⚠️ Не удалось получить информацию об угле")

    # ═══════════════════════════════════════════════════════════════
    # 2. РАСПРЕДЕЛЕНИЕ ПО УГЛАМ
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "-"*70)
    print("📊 2. РАСПРЕДЕЛЕНИЕ ТОЧЕК ПО УГЛАМ")
    print("-"*70)

    # Вычисляем углы для каждой точки
    start_angle_deg = -35
    stop_angle_deg = 35
    total_angle = stop_angle_deg - start_angle_deg
    angle_step = total_angle / len(raw_distances) if raw_distances else 0

    angle_bins = {}
    for i, dist in enumerate(raw_distances):
        angle = start_angle_deg + i * angle_step
        bin_key = int(angle / 5) * 5  # Группируем по 5°
        if bin_key not in angle_bins:
            angle_bins[bin_key] = []
        angle_bins[bin_key].append(dist)

    sorted_angle_bins = sorted(angle_bins.items(), key=lambda x: len(x[1]), reverse=True)

    print("\n   Топ-10 самых заполненных угловых секторов:")
    for i, (angle, points) in enumerate(sorted_angle_bins[:10]):
        count = len(points)
        bar = "█" * min(50, count)
        print(f"   #{i+1}: {angle:>5}° - {angle+5:>5}° -> {count:>3} точек {bar}")

    # ═══════════════════════════════════════════════════════════════
    # 3. УГЛЫ С ТОЧКАМИ ОБЪЕКТА
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "-"*70)
    print("📊 3. УГЛЫ С ТОЧКАМИ ОБЪЕКТА (1400-1600 мм)")
    print("-"*70)

    # Ищем точки в диапазоне объекта
    object_distances = [d for d in raw_distances if 1400 <= d <= 1600]

    if object_distances:
        print(f"\n   Найдено {len(object_distances)} точек объекта (1400-1600 мм)")

        # Находим углы этих точек
        object_angles = []
        for i, dist in enumerate(raw_distances):
            if 1400 <= dist <= 1600:
                angle = start_angle_deg + i * angle_step
                object_angles.append((i, dist, angle))

        if object_angles:
            print(f"\n   Углы точек объекта:")
            min_angle = min(a[2] for a in object_angles)
            max_angle = max(a[2] for a in object_angles)
            print(f"      Минимальный угол: {min_angle:.1f}°")
            print(f"      Максимальный угол: {max_angle:.1f}°")
            print(f"      Разброс: {max_angle - min_angle:.1f}°")

            # Показываем первые 10 точек
            print(f"\n   Первые 10 точек объекта:")
            for i, (idx, dist, angle) in enumerate(object_angles[:10]):
                print(f"      Точка #{i+1}: индекс={idx}, расстояние={dist}мм, угол={angle:.1f}°")
    else:
        print("\n   ❌ Точки объекта не найдены в диапазоне 1400-1600 мм")

    # ═══════════════════════════════════════════════════════════════
    # 4. РЕКОМЕНДАЦИИ
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "-"*70)
    print("📊 4. РЕКОМЕНДАЦИИ")
    print("-"*70)

    if angle_info:
        current_total = angle_info.get('total_angle_deg', 0)

        if current_total > 40:
            print(f"\n   ⚠️ Текущий угол {current_total:.0f}° слишком большой!")
            print(f"      Рекомендуется уменьшить до 20-30°")
            print(f"      Это поможет убрать лишние точки (стены, шум)")
        elif current_total < 10:
            print(f"\n   ⚠️ Текущий угол {current_total:.0f}° слишком маленький!")
            print(f"      Рекомендуется увеличить до 20-30°")
            print(f"      Чтобы видеть объект")
        else:
            print(f"\n   ✅ Текущий угол {current_total:.0f}° оптимальный!")

    # Рекомендации по углам
    print(f"\n   📌 РЕКОМЕНДУЕМЫЕ УГЛЫ:")
    print(f"      20° (-10°…+10°)  - для маленьких объектов")
    print(f"      30° (-15°…+15°)  - для средних объектов (рекомендуется)")
    print(f"      40° (-20°…+20°)  - для больших объектов")
    print(f"      50° (-25°…+25°)  - для очень больших объектов")

    print("\n" + "="*70)
    print("🔬 ТЕСТ ЗАВЕРШЕН")
    print("="*70 + "\n")

    # Отключаемся
    lidar_client.disconnect()
    print("🔌 Отключен")

if __name__ == "__main__":
    try:
        test_angle()
    except KeyboardInterrupt:
        print("\n\n⏹ Прервано пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()