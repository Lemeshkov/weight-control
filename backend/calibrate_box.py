# backend/calibrate_box.py
from services.lidar_client import LidarClient
import time
import json

def calibrate():
    client = LidarClient()
    if not client.connect():
        print("❌ Не удалось подключиться")
        return
    
    # Реальные размеры вашей коробки
    REAL_WIDTH_CM = 40
    REAL_LENGTH_CM = 60
    REAL_HEIGHT_CM = 60
    
    input("\n📦 Поставьте коробку под лидар и нажмите Enter...")
    
    raw_data = client.get_scan_data()
    parsed = client.parse_scan_data(raw_data, filter_angle=True, separate_object=True)
    
    distances = parsed.get('distances_mm', [])
    floor = parsed.get('floor_level_mm', 2000)
    
    if not distances:
        print("❌ Коробка не обнаружена!")
        return
    
    # Расчёт высоты по лидару
    heights = [floor - d for d in distances]
    avg_height_mm = sum(heights) / len(heights)
    measured_height_cm = avg_height_mm / 10
    
    # Калибровочный коэффициент
    calibration_factor = REAL_HEIGHT_CM / measured_height_cm
    
    # Объёмы
    measured_volume_liters = (REAL_WIDTH_CM * REAL_LENGTH_CM * measured_height_cm) / 1000
    real_volume_liters = (REAL_WIDTH_CM * REAL_LENGTH_CM * REAL_HEIGHT_CM) / 1000
    
    print("\n" + "="*50)
    print("📊 РЕЗУЛЬТАТЫ КАЛИБРОВКИ")
    print("="*50)
    
    print(f"\n📐 РАЗМЕРЫ КОРОБКИ:")
    print(f"   Реальная высота: {REAL_HEIGHT_CM} см")
    print(f"   Измеренная высота: {measured_height_cm:.1f} см")
    print(f"   Ошибка: {abs(measured_height_cm - REAL_HEIGHT_CM):.1f} см")
    print(f"   Относительная ошибка: {abs(measured_height_cm - REAL_HEIGHT_CM) / REAL_HEIGHT_CM * 100:.1f}%")
    
    print(f"\n📦 ОБЪЁМ:")
    print(f"   Реальный объём: {real_volume_liters:.0f} литров")
    print(f"   Измеренный объём: {measured_volume_liters:.0f} литров")
    print(f"   Ошибка: {abs(measured_volume_liters - real_volume_liters):.0f} литров")
    
    print(f"\n🔧 КАЛИБРОВОЧНЫЙ КОЭФФИЦИЕНТ: {calibration_factor:.3f}")
    
    # Сохраняем коэффициент
    calib_data = {
        "calibration_factor": calibration_factor,
        "measured_height_cm": measured_height_cm,
        "real_height_cm": REAL_HEIGHT_CM,
        "width_cm": REAL_WIDTH_CM,
        "length_cm": REAL_LENGTH_CM,
        "timestamp": time.time()
    }
    
    with open("calibration.json", "w") as f:
        json.dump(calib_data, f, indent=2)
    
    print(f"\n✅ Коэффициент сохранён в calibration.json")
    
    client.disconnect()

if __name__ == "__main__":
    calibrate()