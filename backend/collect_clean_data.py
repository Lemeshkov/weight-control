# backend/collect_clean_data.py

"""
Сбор чистых данных с лидара после настройки угла 50°
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from services.lidar_client import lidar_client
import json
from datetime import datetime
from collections import Counter

def collect_data():
    print("\n" + "="*70)
    print("📊 СБОР ЧИСТЫХ ДАННЫХ С ЛИДАРА")
    print("="*70 + "\n")

    # Подключаемся
    if not lidar_client.is_connected:
        print("🔌 Подключаемся...")
        if not lidar_client.connect():
            print("❌ Ошибка подключения")
            return
        print("✅ Подключено")

    # Проверяем угол
    print("\n📡 Проверка угла...")
    angle_info = lidar_client.get_current_angle_range()

    if angle_info:
        start = angle_info.get('start_angle_deg', 0)
        stop = angle_info.get('stop_angle_deg', 0)
        total = angle_info.get('total_angle_deg', 0)

        print(f"\n📊 ТЕКУЩИЙ УГОЛ:")
        print(f"   Стартовый: {start:.1f}°")
        print(f"   Конечный: {stop:.1f}°")
        print(f"   Общий: {total:.1f}°")

        if total != 50:
            print(f"⚠️ Угол не 50°! Запустите set_angle.py снова")
            lidar_client.disconnect()
            return

    # Получаем данные
    print("\n📡 Получаем данные сканирования...")
    scan_data = lidar_client.get_scan_data()

    if not scan_data:
        print("❌ Нет данных")
        lidar_client.disconnect()
        return

    # Парсим сырые данные
    raw_distances = lidar_client.parse_raw_data(scan_data)
    print(f"\n📊 Сырых точек: {len(raw_distances)}")

    # Фильтруем шум (только валидные расстояния)
    valid_distances = [d for d in raw_distances if 1000 <= d <= 3000]
    print(f"📊 После фильтрации шума: {len(valid_distances)}")

    if not valid_distances:
        print("❌ Нет валидных точек!")
        lidar_client.disconnect()
        return

    # ═══════════════════════════════════════════════════════════
    # АНАЛИЗ ДАННЫХ
    # ═══════════════════════════════════════════════════════════

    print("\n" + "-"*70)
    print("📊 СТАТИСТИКА")
    print("-"*70)

    print(f"\n   Количество точек: {len(valid_distances)}")
    print(f"   Минимальное: {min(valid_distances)} мм")
    print(f"   Максимальное: {max(valid_distances)} мм")
    print(f"   Среднее: {sum(valid_distances)/len(valid_distances):.0f} мм")
    print(f"   Медиана: {sorted(valid_distances)[len(valid_distances)//2]} мм")

    # ═══════════════════════════════════════════════════════════
    # ГИСТОГРАММА (бины по 50 мм)
    # ═══════════════════════════════════════════════════════════

    bins = {}
    for d in valid_distances:
        bin_key = int(d / 50) * 50
        bins[bin_key] = bins.get(bin_key, 0) + 1

    print("\n" + "-"*70)
    print("📊 ТОП-10 САМЫХ ЗАПОЛНЕННЫХ БИНОВ")
    print("-"*70)

    sorted_bins = sorted(bins.items(), key=lambda x: x[1], reverse=True)
    for i, (bin_val, count) in enumerate(sorted_bins[:10]):
        bar = "█" * min(50, count)
        percentage = (count / len(valid_distances)) * 100
        print(f"   #{i+1:2d}: {bin_val:>5} мм -> {count:>3} точек ({percentage:>5.1f}%) {bar}")

    # ═══════════════════════════════════════════════════════════
    # ПОИСК ОБЪЕКТА И ПОЛА
    # ═══════════════════════════════════════════════════════════

    FLOOR_LEVEL = 2792  # мм - фиксированный пол

    # Точки пола (2700-2800 мм)
    floor_points = [d for d in valid_distances if 2700 <= d <= 2800]
    print(f"\n🏗️ ПОЛ:")
    print(f"   Точек в диапазоне 2700-2800 мм: {len(floor_points)}")
    if floor_points:
        print(f"   Среднее: {sum(floor_points)/len(floor_points):.0f} мм")

    # Ищем объект - самый частый бин (кроме пола)
    object_bin = None
    object_count = 0

    for bin_val, count in sorted_bins:
        # Пропускаем пол (2700-2800 мм)
        if 2700 <= bin_val <= 2800:
            continue
        # Пропускаем слишком близкие (< 1200 мм) - шум
        if bin_val < 1200:
            continue
        if count > object_count:
            object_count = count
            object_bin = bin_val

    print("\n" + "-"*70)
    print("📦 ОБЪЕКТ")
    print("-"*70)

    if object_bin and object_count > 3:
        # Собираем все точки объекта
        object_points = [d for d in valid_distances if object_bin - 25 <= d <= object_bin + 25]
        object_height = FLOOR_LEVEL - object_bin

        print(f"\n   Обнаружен объект:")
        print(f"      Бин: {object_bin} мм")
        print(f"      Точек: {len(object_points)}")
        print(f"      Высота от пола: {object_height} мм ({object_height/10:.1f} см)")

        # Определяем статус по порогам
        if len(object_points) <= 10:
            status = "🟢 ПУСТО"
            confidence = 90
            reason = f"Точек {len(object_points)} <= 10 (пусто)"
        elif len(object_points) >= 15:
            status = "🟠 ЗАПОЛНЕНО"
            confidence = 85
            reason = f"Точек {len(object_points)} >= 15 (заполнено)"
        else:
            status = "🟡 ПРОМЕЖУТОЧНОЕ"
            confidence = 60
            reason = f"Точек {len(object_points)} между 10 и 15"

        print(f"      Статус: {status}")
        print(f"      Уверенность: {confidence}%")
        print(f"      Причина: {reason}")

        # Проверяем соответствие коробке M
        print(f"\n   📦 КОРОБКА M (35×65×37 см):")
        print(f"      Ожидаемая высота: 370 мм")
        print(f"      Измеренная: {object_height} мм")

        if 320 <= object_height <= 400:
            print(f"      ✅ СООТВЕТСТВУЕТ!")
        else:
            print(f"      ❌ НЕ СООТВЕТСТВУЕТ (ожидается 370 мм)")
            if object_height < 200:
                print(f"      ⚠️ Слишком низкая - возможно, пустая коробка")
            elif object_height > 500:
                print(f"      ⚠️ Слишком высокая - возможно, нужна калибровка")

        # Сохраняем данные
        data = {
            "timestamp": datetime.now().isoformat(),
            "angle": {
                "start": start if angle_info else 0,
                "stop": stop if angle_info else 0,
                "total": total if angle_info else 0
            },
            "points": {
                "total": len(valid_distances),
                "floor": len(floor_points),
                "object": len(object_points)
            },
            "object": {
                "bin_mm": object_bin,
                "height_mm": object_height,
                "height_cm": object_height / 10
            },
            "status": {
                "label": status,
                "confidence": confidence,
                "reason": reason
            },
            "bins": sorted_bins[:20]
        }

        filename = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"\n💾 Данные сохранены в {filename}")

    else:
        print(f"\n❌ Объект не обнаружен!")
        if sorted_bins:
            print(f"   Самый частый бин: {sorted_bins[0][0]} мм ({sorted_bins[0][1]} точек)")

    print("\n" + "="*70)

    lidar_client.disconnect()
    print("\n🔌 Отключено")

if __name__ == "__main__":
    collect_data()