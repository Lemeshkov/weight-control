from services.vehicle_profiles import vehicle_profiles

@classmethod
def classify(cls, distances_mm: List[int]) -> Dict[str, Any]:
    """Классифицирует объект по данным сканирования"""
    if not distances_mm:
        return {
            "object_type": "unknown",
            "confidence": 0,
            "mode": "auto",
            "reason": "Нет данных"
        }
    
    points_count = len(distances_mm)
    spread = max(distances_mm) - min(distances_mm) if distances_mm else 0
    
    # ✅ Ищем совпадение в базе профилей
    match_result = vehicle_profiles.find_matching_profile(distances_mm)
    
    if match_result["profile"]:
        profile = match_result["profile"]
        confidence = match_result["confidence"]
        
        # Определяем, пустой ли объект
        avg_height = sum(distances_mm) / len(distances_mm) if distances_mm else 0
        is_empty = False
        
        # Для грузовиков: если высота близка к высоте пустого кузова
        if profile.vehicle_type in ["truck", "trailer", "wagon"]:
            if abs(avg_height - profile.empty_height_mm) < 100:
                is_empty = True
                subtype = "empty"
            else:
                is_empty = False
                subtype = "filled"
        else:
            # Для коробки: определяем по наличию предметов
            is_empty = points_count < 20 or spread < 100
            subtype = "empty" if is_empty else "filled"
        
        # Определяем режим для ObjectDetector
        mode = profile.vehicle_type if profile.vehicle_type in ["box", "truck"] else "auto"
        
        # Корректируем размеры
        if profile.vehicle_type in ["truck", "trailer", "wagon"]:
            # Используем реальные размеры из профиля
            pass
        
        return {
            "object_type": profile.vehicle_type,
            "subtype": subtype,
            "is_empty": is_empty,
            "confidence": confidence,
            "mode": mode,
            "reason": f"Распознан как {profile.name} (совпадение {confidence}%)",
            "profile": profile.to_dict(),
            "features": {
                "points_count": points_count,
                "spread_mm": spread,
                "avg_height_mm": avg_height
            }
        }
    
    # Если не найден профиль - fallback на старую логику
    logger.warning(f"⚠️ Не найден профиль для точек={points_count}, разброс={spread}")
    return {
        "object_type": "unknown",
        "confidence": 30,
        "mode": "auto",
        "reason": "Не найден подходящий профиль",
        "features": {
            "points_count": points_count,
            "spread_mm": spread
        }
    }