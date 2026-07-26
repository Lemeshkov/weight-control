# backend/debug_lidar.py

import sys
import os
import logging
from pathlib import Path

# Добавляем backend в путь
sys.path.insert(0, str(Path(__file__).parent))

from services.lidar_client import lidar_client
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def diagnose_lidar_data():
    """
    Диагностический скрипт для анализа данных лидара.
    Показывает:
    1. Сколько точек на каждом расстоянии
    2. Где находится реальный объект
    3. Что такое "пол" по данным лидара
    """

    print("\n" + "="*70)
    print("🔬 ДИАГНОСТИКА ДАННЫХ ЛИДАРА")
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
    # 1. ПРЯМОЙ АНАЛИЗ БЕЗ ФИЛЬТРАЦИИ
    # ═══════════════════════════════════════════════════════════════

    print("\n" + "-"*70)
    print("📊 1. АНАЛИЗ СЫРЫХ ДАННЫХ (БЕЗ ФИЛЬТРАЦИИ)")
    print("-"*70)

    # Статистика
    min_dist = min(raw_distances)
    max_dist = max(raw_distances)
    avg_dist = sum(raw_distances) / len(raw_distances)

    print(f"\n📐 Статистика:")
    print(f"   Минимальное расстояние: {min_dist} мм")
    print(f"   Максимальное расстояние: {max_dist} мм")
    print(f"   Среднее расстояние: {avg_dist:.0f} мм")

    # Гистограмма (по 50 мм)
    print(f"\n📊 Гистограмма (по 50 мм):")
    bins = {}
    for d in raw_distances:
        bin_key = int(d / 50) * 50
        bins[bin_key] = bins.get(bin_key, 0) + 1

    # Сортируем по убыванию
    sorted_bins = sorted(bins.items(), key=lambda x: x[1], reverse=True)

    print("   Топ-10 самых частых бинов:")
    for i, (bin_val, count) in enumerate(sorted_bins[:10]):
        bar = "█" * min(50, count)
        print(f"   #{i+1}: {bin_val:>6} мм -> {count:>3} точек {bar}")

    # ═══════════════════════════════════════════════════════════════
    # 2. АНАЛИЗ ПОСЛЕ ФИЛЬТРАЦИИ MIN_VALID_DISTANCE
    # ═══════════════════════════════════════════════════════════════

    print("\n" + "-"*70)
    print(f"📊 2. АНАЛИЗ ПОСЛЕ ФИЛЬТРАЦИИ (>{lidar_client.MIN_VALID_DISTANCE} мм)")
    print("-"*70)

    filtered_distances = [d for d in raw_distances
                            if d > lidar_client.MIN_VALID_DISTANCE]

    print(f"\n📐 Статистика:")
    print(f"   Всего точек: {len(filtered_distances)} (из {len(raw_distances)})")
    print(f"   Отброшено: {len(raw_distances) - len(filtered_distances)} точек (< {lidar_client.MIN_VALID_DISTANCE} мм)")

    if filtered_distances:
        min_dist = min(filtered_distances)
        max_dist = max(filtered_distances)
        avg_dist = sum(filtered_distances) / len(filtered_distances)
        print(f"   Минимальное расстояние: {min_dist} мм")
        print(f"   Максимальное расстояние: {max_dist} мм")
        print(f"   Среднее расстояние: {avg_dist:.0f} мм")

    # ═══════════════════════════════════════════════════════════════
    # 3. ПОИСК ОБЪЕКТА (кластер)
    # ═══════════════════════════════════════════════════════════════

    print("\n" + "-"*70)
    print("📊 3. ПОИСК ОБЪЕКТА (кластер)")
    print("-"*70)

    # Используем фиксированный пол
    FLOOR_LEVEL = 2792
    OBJECT_THRESHOLD = 80

    # Ищем точки ближе к лидару, чем пол
    object_candidates = []
    for i, d in enumerate(filtered_distances):
        if d < FLOOR_LEVEL - OBJECT_THRESHOLD:
            object_candidates.append((i, d))

    print(f"\n🎯 Кандидатов в объект: {len(object_candidates)}")

    if object_candidates:
        # Ищем кластер
        clusters = []
        current_cluster = [object_candidates[0]]

        for i in range(1, len(object_candidates)):
            if object_candidates[i][0] - object_candidates[i-1][0] <= 5:
                current_cluster.append(object_candidates[i])
            else:
                clusters.append(current_cluster)
                current_cluster = [object_candidates[i]]

        if current_cluster:
            clusters.append(current_cluster)

        # Находим самый большой кластер
        best_cluster = max(clusters, key=len)
        cluster_distances = [d for _, d in best_cluster]

        print(f"\n📦 Самый большой кластер: {len(best_cluster)} точек")
        print(f"   Расстояния: {min(cluster_distances)} - {max(cluster_distances)} мм")
        print(f"   Разброс: {max(cluster_distances) - min(cluster_distances)} мм")

        # Высота от пола
        min_dist = min(cluster_distances)
        object_height = FLOOR_LEVEL - min_dist
        print(f"\n📏 Высота объекта: {object_height} мм (пол={FLOOR_LEVEL} мм)")

        # ═══════════════════════════════════════════════════════════════
        # 4. СРАВНЕНИЕ С РАЗНЫМИ УРОВНЯМИ ПОЛА
        # ═══════════════════════════════════════════════════════════════

        print("\n" + "-"*70)
        print("📊 4. СРАВНЕНИЕ С РАЗНЫМИ УРОВНЯМИ ПОЛА")
        print("-"*70)

        floor_levels = [1450, 2792, 2792, 2792]  # разные варианты
        labels = ["1450 (гистограмма)", "2792 (фиксированный)", "2792+1000", "2792-1000"]

        print(f"\n{'Уровень пола':<20} {'Высота объекта':<20} {'Описание'}")
        print("-"*60)

        for label, floor in zip(labels, floor_levels):
            height = floor - min_dist
            print(f"{label:<20} {height:>8} мм")

        # ═══════════════════════════════════════════════════════════════
        # 5. РЕКОМЕНДАЦИИ
        # ═══════════════════════════════════════════════════════════════

        print("\n" + "-"*70)
        print("📊 5. РЕКОМЕНДАЦИИ")
        print("-"*70)

        # Проверяем, где находится объект
        if min_dist < 1500:
            print(f"\n⚠️ Объект находится на расстоянии {min_dist} мм от лидара")
            print("   Это МЕНЬШЕ 1500 мм - возможно, это шум или неправильные данные")
            print("   Рекомендация: проверить настройки MIN_VALID_DISTANCE")
        elif 1500 <= min_dist <= 2500:
            print(f"\n✅ Объект находится на расстоянии {min_dist} мм от лидара")
            print("   Это в диапазоне 1500-2500 мм - вероятно, реальный объект")
            print(f"   Высота от пола ({FLOOR_LEVEL} мм): {object_height} мм")
        else:
            print(f"\n✅ Объект находится на расстоянии {min_dist} мм от лидара")
            print("   Это БОЛЬШЕ 2500 мм - очень близко к полу")
            print(f"   Высота от пола ({FLOOR_LEVEL} мм): {object_height} мм")

        print(f"\n📌 Итоговая рекомендация:")
        if object_height < 100:
            print("   Объект почти пустой (высота < 100 мм)")
        elif object_height < 200:
            print("   Объект частично заполнен (высота 100-200 мм)")
        elif object_height < 300:
            print("   Объект заполнен наполовину (высота 200-300 мм)")
        else:
            print("   Объект почти полный (высота > 300 мм)")

    else:
        print("\n❌ Объект не найден!")
        print("   Нет точек ближе к лидару, чем пол")

    # ═══════════════════════════════════════════════════════════════
    # 6. ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ
    # ═══════════════════════════════════════════════════════════════

    print("\n" + "-"*70)
    print("📊 6. ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ")
    print("-"*70)

    print(f"\n🔧 Настройки лидара:")
    print(f"   MIN_VALID_DISTANCE: {lidar_client.MIN_VALID_DISTANCE} мм")
    print(f"   MAX_VALID_DISTANCE: {lidar_client.MAX_VALID_DISTANCE} мм")
    print(f"   FLOOR_LEVEL: {lidar_client.FLOOR_LEVEL} мм")
    print(f"   FLOOR_THRESHOLD: {lidar_client.FLOOR_THRESHOLD} мм")

    print("\n" + "="*70)
    print("🔬 ДИАГНОСТИКА ЗАВЕРШЕНА")
    print("="*70 + "\n")


if __name__ == "__main__":
    try:
        diagnose_lidar_data()
    except KeyboardInterrupt:
        print("\n\n⏹ Прервано пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if lidar_client.is_connected:
            lidar_client.disconnect()