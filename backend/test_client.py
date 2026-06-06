# backend/test_client.py
from services.lidar_client import LidarClient
import json

c = LidarClient()
if c.connect():
    data = c.get_scan_data()
    if data:
        parsed = c.parse_scan_data(data)
        print('✅ УСПЕХ!')
        print(f'Точек: {parsed.get("points_count", 0)}')
        print(f'Расстояния (первые 10): {parsed.get("distances_mm", [])[:10]}')
        print(f'Мин: {parsed.get("min_distance_mm")} мм')
        print(f'Макс: {parsed.get("max_distance_mm")} мм')
    else:
        print('❌ Нет данных')
else:
    print('❌ Не подключен')

c.disconnect()