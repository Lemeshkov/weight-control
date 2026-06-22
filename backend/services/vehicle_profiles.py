"""
База эталонов транспортных средств и объектов
"""
from typing import Dict, List, Any, Optional, Tuple
import json
import logging

logger = logging.getLogger(__name__)

class VehicleProfile:
    """Профиль транспортного средства или объекта"""
    
    def __init__(
        self,
        name: str,
        vehicle_type: str,  # "truck", "box", "trailer", "wagon"
        brand: Optional[str] = None,
        model: Optional[str] = None,
        length_m: float = 0,
        width_m: float = 0,
        height_m: float = 0,
        empty_height_mm: float = 0,  # высота пустого объекта от пола
        filled_height_mm: float = 0,  # высота заполненного объекта
        points_range: tuple = (0, 1000),
        spread_range: tuple = (0, 10000),
        floor_level_mm: int = 2000,
        profile_type: str = "standard",
        # Новые параметры для коробок
        box_type: str = "unknown",  # "small", "medium", "large"
        empty_points_ratio: float = 0.4,  # Если точек меньше 40% от ожидаемых - пусто
        filled_points_ratio: float = 0.7,  # Если точек больше 70% - заполнено
        min_points_for_filled: int = 15,   # Минимум точек для определения заполненности
        # ⭐ УДАЛЯЕМ empty_threshold_mm и filled_threshold_mm (они больше не используются)
    ):
        self.name = name
        self.vehicle_type = vehicle_type
        self.brand = brand
        self.model = model
        self.length_m = length_m
        self.width_m = width_m
        self.height_m = height_m
        self.empty_height_mm = empty_height_mm
        self.filled_height_mm = filled_height_mm if filled_height_mm > 0 else height_m * 1000
        self.points_range = points_range
        self.spread_range = spread_range
        self.floor_level_mm = floor_level_mm
        self.profile_type = profile_type
        self.box_type = box_type
        self.empty_points_ratio = empty_points_ratio
        self.filled_points_ratio = filled_points_ratio
        self.min_points_for_filled = min_points_for_filled
        
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "vehicle_type": self.vehicle_type,
            "brand": self.brand,
            "model": self.model,
            "length_m": self.length_m,
            "width_m": self.width_m,
            "height_m": self.height_m,
            "empty_height_mm": self.empty_height_mm,
            "filled_height_mm": self.filled_height_mm,
            "points_range": self.points_range,
            "spread_range": self.spread_range,
            "floor_level_mm": self.floor_level_mm,
            "profile_type": self.profile_type,
            "box_type": self.box_type,
            "empty_points_ratio": self.empty_points_ratio,
            "filled_points_ratio": self.filled_points_ratio,
            "min_points_for_filled": self.min_points_for_filled,
        }
    
    def is_empty(self, object_height_mm: float, points_count: int) -> Tuple[bool, float]:
        """
        Определяет, пустой ли объект
        ⭐ НОВАЯ ЛОГИКА: используем КОЛИЧЕСТВО ТОЧЕК, а не высоту!
        
        Returns: (is_empty, confidence)
        """
        # Вычисляем ожидаемое количество точек для этого профиля
        expected_points = (self.points_range[0] + self.points_range[1]) / 2
        
        # ⭐ ГЛАВНОЕ: считаем отношение фактических точек к ожидаемым
        points_ratio = points_count / expected_points if expected_points > 0 else 0
        
        # === ОСНОВНАЯ ЛОГИКА ПО КОЛИЧЕСТВУ ТОЧЕК ===
        
        # 1. Если точек очень мало - объект ПУСТОЙ
        if points_ratio < self.empty_points_ratio:
            confidence = min(95, 70 + (1 - points_ratio / self.empty_points_ratio) * 25)
            return True, confidence
        
        # 2. Если точек достаточно много и объект высокий - ЗАПОЛНЕН
        if points_ratio > self.filled_points_ratio and points_count > self.min_points_for_filled:
            confidence = min(95, 70 + (points_ratio - self.filled_points_ratio) / (1 - self.filled_points_ratio) * 25)
            return False, confidence
        
        # 3. Промежуточная зона - анализируем дополнительно
        
        # 3a. Если точек мало, но объект высокий - скорее всего видим только стенку (пусто)
        if points_ratio < 0.5 and object_height_mm > 100:
            return True, 75.0
        
        # 3b. Если точек средне, но объект низкий - скорее всего пусто
        if points_ratio < 0.6 and object_height_mm < 50:
            return True, 80.0
        
        # 3c. Если точек достаточно, но объект низкий - возможно пусто
        if points_ratio > 0.6 and object_height_mm < 50:
            return False, 65.0
        
        # 4. Неопределенность - склоняемся к пустоте (безопаснее)
        if points_ratio < 0.6:
            return True, 60.0
        else:
            return False, 60.0
    
    def is_empty_detailed(self, object_height_mm: float, points_count: int) -> Dict[str, Any]:
        """
        Детальный анализ пустоты с пояснениями
        """
        expected_points = (self.points_range[0] + self.points_range[1]) / 2
        points_ratio = points_count / expected_points if expected_points > 0 else 0
        
        is_empty, confidence = self.is_empty(object_height_mm, points_count)
        
        # Формируем детальное объяснение
        reasons = []
        
        if points_ratio < self.empty_points_ratio:
            reasons.append(f"Точек {points_count} ({points_ratio*100:.0f}%) меньше порога {self.empty_points_ratio*100:.0f}%")
            if object_height_mm > 100:
                reasons.append(f"Высота {object_height_mm:.0f}мм, вероятно видна только стенка")
        elif points_ratio > self.filled_points_ratio:
            reasons.append(f"Точек {points_count} ({points_ratio*100:.0f}%) больше порога {self.filled_points_ratio*100:.0f}%")
        else:
            reasons.append(f"Точек {points_count} ({points_ratio*100:.0f}%) в промежуточной зоне")
        
        if object_height_mm < 50:
            reasons.append(f"Низкая высота {object_height_mm:.0f}мм")
        
        return {
            "is_empty": is_empty,
            "confidence": confidence,
            "points_count": points_count,
            "expected_points": expected_points,
            "points_ratio": points_ratio,
            "object_height_mm": object_height_mm,
            "reasons": reasons,
            "diagnostic": {
                "empty_threshold": self.empty_points_ratio * 100,
                "filled_threshold": self.filled_points_ratio * 100,
                "min_points_for_filled": self.min_points_for_filled,
            }
        }


class VehicleProfilesDB:
    """База эталонов транспортных средств"""
    
    def __init__(self):
        self.profiles: Dict[str, VehicleProfile] = {}
        self._init_default_profiles()
    
    def _init_default_profiles(self):
        """Инициализация стандартных профилей"""
        
        # ============================================================
        # 📦 ПРОФИЛИ КОРОБОК (реальные размеры)
        # ============================================================
        
        # 1. Коробка малая S: 20x31x25 см
        self.add_profile(VehicleProfile(
            name="Коробка S (20x31x25)",
            vehicle_type="box",
            brand="BOX",
            model="S-203125",
            length_m=0.31,
            width_m=0.20,
            height_m=0.25,
            empty_height_mm=15,      # Дно коробки
            filled_height_mm=230,    # Полная
            points_range=(8, 40),    # Ожидаемое количество точек
            spread_range=(50, 300),
            floor_level_mm=1750,
            profile_type="box",
            box_type="small",
            empty_points_ratio=0.4,   # < 40% точек = пусто
            filled_points_ratio=0.7,  # > 70% точек = заполнено
            min_points_for_filled=12, # Минимум точек для заполненности
        ))
        
        # 2. Коробка средняя M: 35x65x37 см
        self.add_profile(VehicleProfile(
            name="Коробка M (35x65x37)",
            vehicle_type="box",
            brand="BOX",
            model="M-356537",
            length_m=0.65,
            width_m=0.35,
            height_m=0.37,
            empty_height_mm=15,
            filled_height_mm=350,
            points_range=(12, 60),
            spread_range=(80, 400),
            floor_level_mm=1700,
            profile_type="box",
            box_type="medium",
            empty_points_ratio=0.4,
            filled_points_ratio=0.7,
            min_points_for_filled=15,
        ))
        
        # 3. Коробка большая L: 40x60x60 см
        self.add_profile(VehicleProfile(
            name="Коробка L (40x60x60)",
            vehicle_type="box",
            brand="BOX",
            model="L-406060",
            length_m=0.60,
            width_m=0.40,
            height_m=0.60,
            empty_height_mm=20,
            filled_height_mm=550,
            points_range=(15, 80),
            spread_range=(100, 600),
            floor_level_mm=1650,
            profile_type="box",
            box_type="large",
            empty_points_ratio=0.4,
            filled_points_ratio=0.7,
            min_points_for_filled=20,
        ))
        
        # 4. Тестовая коробка
        self.add_profile(VehicleProfile(
            name="Тестовая коробка (50x40x25)",
            vehicle_type="box",
            brand="TEST",
            model="BOX-TEST",
            length_m=0.50,
            width_m=0.40,
            height_m=0.25,
            empty_height_mm=15,
            filled_height_mm=230,
            points_range=(10, 50),
            spread_range=(60, 350),
            floor_level_mm=1700,
            profile_type="calibration",
            box_type="test",
            empty_points_ratio=0.4,
            filled_points_ratio=0.7,
            min_points_for_filled=12,
        ))
        
        # ============================================================
        # 🚛 ПРОФИЛИ ГРУЗОВИКОВ
        # ============================================================
        
        self.add_profile(VehicleProfile(
            name="КАМАЗ 65115",
            vehicle_type="truck",
            brand="КАМАЗ",
            model="65115",
            length_m=6.0,
            width_m=2.5,
            height_m=2.0,
            empty_height_mm=300,
            filled_height_mm=1800,
            points_range=(100, 400),
            spread_range=(500, 2000),
            floor_level_mm=2000,
            profile_type="dump_truck",
            empty_points_ratio=0.3,
            filled_points_ratio=0.6,
            min_points_for_filled=50,
        ))
        
        self.add_profile(VehicleProfile(
            name="КАМАЗ 6520",
            vehicle_type="truck",
            brand="КАМАЗ",
            model="6520",
            length_m=6.5,
            width_m=2.55,
            height_m=2.2,
            empty_height_mm=350,
            filled_height_mm=2000,
            points_range=(120, 450),
            spread_range=(600, 2200),
            floor_level_mm=2000,
            profile_type="dump_truck",
            empty_points_ratio=0.3,
            filled_points_ratio=0.6,
            min_points_for_filled=50,
        ))
        
        self.add_profile(VehicleProfile(
            name="Урал 5557",
            vehicle_type="truck",
            brand="Урал",
            model="5557",
            length_m=5.8,
            width_m=2.5,
            height_m=1.8,
            empty_height_mm=250,
            filled_height_mm=1600,
            points_range=(100, 350),
            spread_range=(500, 1800),
            floor_level_mm=2000,
            profile_type="dump_truck",
            empty_points_ratio=0.3,
            filled_points_ratio=0.6,
            min_points_for_filled=50,
        ))
        
        self.add_profile(VehicleProfile(
            name="МАЗ 5516",
            vehicle_type="truck",
            brand="МАЗ",
            model="5516",
            length_m=6.2,
            width_m=2.5,
            height_m=2.1,
            empty_height_mm=320,
            filled_height_mm=1900,
            points_range=(110, 420),
            spread_range=(550, 2100),
            floor_level_mm=2000,
            profile_type="dump_truck",
            empty_points_ratio=0.3,
            filled_points_ratio=0.6,
            min_points_for_filled=50,
        ))
        
        # ============================================================
        # 🚆 ПРОЧИЕ
        # ============================================================
        
        self.add_profile(VehicleProfile(
            name="Прицеп самосвальный",
            vehicle_type="trailer",
            brand="Trailer",
            model="2ПТС-4",
            length_m=7.0,
            width_m=2.5,
            height_m=2.3,
            empty_height_mm=400,
            filled_height_mm=2100,
            points_range=(150, 500),
            spread_range=(700, 2500),
            floor_level_mm=2000,
            profile_type="trailer",
            empty_points_ratio=0.3,
            filled_points_ratio=0.6,
            min_points_for_filled=50,
        ))
        
        self.add_profile(VehicleProfile(
            name="Вагон-самосвал",
            vehicle_type="wagon",
            brand="Railway",
            model="ВС-105",
            length_m=10.0,
            width_m=2.8,
            height_m=2.5,
            empty_height_mm=500,
            filled_height_mm=2300,
            points_range=(200, 800),
            spread_range=(1000, 3000),
            floor_level_mm=2000,
            profile_type="wagon",
            empty_points_ratio=0.3,
            filled_points_ratio=0.6,
            min_points_for_filled=80,
        ))
        
        logger.info(f"✅ Загружено {len(self.profiles)} профилей")
    
    def add_profile(self, profile: VehicleProfile):
        """Добавить профиль в базу"""
        self.profiles[profile.name] = profile
        logger.info(f"➕ Добавлен профиль: {profile.name}")
    
    def get_profile(self, name: str) -> Optional[VehicleProfile]:
        """Получить профиль по имени"""
        return self.profiles.get(name)
    
    def find_matching_profile(self, distances_mm: List[int], floor_level_mm: int = None) -> Dict[str, Any]:
        """
        Найти наиболее подходящий профиль по данным сканирования
        """
        if not distances_mm or len(distances_mm) < 5:
            return {
                "profile": None,
                "confidence": 0,
                "reason": "Нет данных",
                "matches": []
            }
        
        points_count = len(distances_mm)
        spread = max(distances_mm) - min(distances_mm) if distances_mm else 0
        avg_height = sum(distances_mm) / len(distances_mm) if distances_mm else 0
        
        object_height = 0
        if floor_level_mm:
            min_dist = min(distances_mm)
            object_height = floor_level_mm - min_dist if floor_level_mm > min_dist else 0
        
        matches = []
        
        for name, profile in self.profiles.items():
            score = 0
            reasons = []
            
            # 1. Количество точек
            p_min, p_max = profile.points_range
            if p_min <= points_count <= p_max:
                score += 30
                reasons.append(f"точек {points_count} в диапазоне [{p_min}-{p_max}]")
            elif points_count < p_min:
                score -= 5
            elif points_count > p_max:
                score -= 5
            
            # 2. Разброс расстояний (ширина объекта)
            s_min, s_max = profile.spread_range
            if s_min <= spread <= s_max:
                score += 30
                reasons.append(f"разброс {spread}мм в диапазоне [{s_min}-{s_max}]")
            elif spread < s_min:
                score -= 5
            elif spread > s_max:
                score -= 5
            
            # 3. Высота объекта (если известна)
            if object_height > 0:
                expected_height = profile.height_m * 1000
                height_diff = abs(object_height - expected_height)
                
                if height_diff < 50:  # < 5см
                    score += 40
                    reasons.append(f"высота {object_height:.0f}мм совпадает с {expected_height:.0f}мм")
                elif height_diff < 100:  # < 10см
                    score += 20
                    reasons.append(f"высота {object_height:.0f}мм близка к {expected_height:.0f}мм")
                else:
                    score -= 10
            
            matches.append({
                "name": name,
                "profile": profile,
                "score": score,
                "reasons": reasons,
                "vehicle_type": profile.vehicle_type,
                "object_height": object_height
            })
        
        # Сортируем по баллам
        matches.sort(key=lambda x: x["score"], reverse=True)
        
        best_match = matches[0] if matches else None
        
        # Если лучший профиль - коробка, но есть и грузовик с высоким баллом
        if best_match and best_match["profile"].vehicle_type == "box":
            truck_match = next((m for m in matches if m["profile"].vehicle_type == "truck" and m["score"] > 40), None)
            if truck_match and truck_match["score"] > best_match["score"]:
                best_match = truck_match
        
        logger.info(f"🔍 Лучший профиль: {best_match['name'] if best_match else 'нет'} (score: {best_match['score'] if best_match else 0})")
        
        return {
            "profile": best_match["profile"] if best_match else None,
            "confidence": max(0, best_match["score"]) if best_match else 0,
            "reason": best_match["reasons"][0] if best_match and best_match["reasons"] else "нет совпадений",
            "matches": matches[:3],
            "object_height_mm": object_height
        }
    
    def get_all_profiles(self) -> List[Dict]:
        """Получить все профили для отображения"""
        return [p.to_dict() for p in self.profiles.values()]
    
    def get_profiles_by_type(self, vehicle_type: str) -> List[Dict]:
        """Получить профили определенного типа"""
        return [
            p.to_dict() for p in self.profiles.values() 
            if p.vehicle_type == vehicle_type
        ]
    
    def get_box_info_from_profile(self, profile) -> Dict[str, Any]:
        """
        Извлекает информацию о типе коробки из профиля
        """
        if not profile:
            return {
                "box_type": "unknown",
                "box_label": "?",
                "box_name": "Неизвестная",
                "size_mm": {"width": 0, "depth": 0, "height": 0},
                "size_cm": {"width": 0, "depth": 0, "height": 0},
                "detected": False,
                "confidence": 0,
                "profile_name": None
            }
        
        # Если это не коробка - возвращаем базовую информацию
        if profile.vehicle_type != "box":
            return {
                "box_type": "none",
                "box_label": "-",
                "box_name": profile.name.split()[0] if profile.name else "Транспорт",
                "size_mm": {
                    "width": int(profile.width_m * 1000),
                    "depth": int(profile.length_m * 1000),
                    "height": int(profile.height_m * 1000)
                },
                "size_cm": {
                    "width": round(profile.width_m * 100, 1),
                    "depth": round(profile.length_m * 100, 1),
                    "height": round(profile.height_m * 100, 1)
                },
                "detected": True,
                "confidence": 80,
                "profile_name": profile.name,
                "vehicle_type": profile.vehicle_type
            }
        
        # Определяем тип по box_type
        box_type = getattr(profile, "box_type", "unknown")
        
        # Маппинг типов
        type_map = {
            "small": {"label": "S", "name": "Малая", "emoji": "📦"},
            "medium": {"label": "M", "name": "Средняя", "emoji": "📦"},
            "large": {"label": "L", "name": "Большая", "emoji": "📦"},
            "test": {"label": "T", "name": "Тестовая", "emoji": "🧪"},
        }
        
        info = type_map.get(box_type, {"label": "?", "name": "Неизвестная", "emoji": "📦"})
        
        return {
            "box_type": box_type,
            "box_label": info["label"],
            "box_name": info["name"],
            "emoji": info["emoji"],
            "size_mm": {
                "width": int(profile.width_m * 1000),
                "depth": int(profile.length_m * 1000),
                "height": int(profile.height_m * 1000)
            },
            "size_cm": {
                "width": round(profile.width_m * 100, 1),
                "depth": round(profile.length_m * 100, 1),
                "height": round(profile.height_m * 100, 1)
            },
            "detected": True,
            "confidence": 85,
            "profile_name": profile.name,
            "vehicle_type": profile.vehicle_type,
            "brand": profile.brand,
            "model": profile.model
        }


# Глобальный экземпляр базы
vehicle_profiles = VehicleProfilesDB()