"""
База эталонов транспортных средств и объектов

ВНИМАНИЕ! Это ТЕСТОВАЯ БАЗА для разработки!
Реальные размеры будут получены из калибровки.
"""

from typing import Dict, List, Any, Optional
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
        empty_height_mm: float = 0,  # высота пустого кузова от пола
        points_range: tuple = (0, 1000),  # ожидаемое количество точек
        spread_range: tuple = (0, 10000),  # разброс расстояний
        floor_level_mm: int = 2000,  # уровень пола
        profile_type: str = "standard"
    ):
        self.name = name
        self.vehicle_type = vehicle_type
        self.brand = brand
        self.model = model
        self.length_m = length_m
        self.width_m = width_m
        self.height_m = height_m
        self.empty_height_mm = empty_height_mm
        self.points_range = points_range
        self.spread_range = spread_range
        self.floor_level_mm = floor_level_mm
        self.profile_type = profile_type
        
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
            "points_range": self.points_range,
            "spread_range": self.spread_range,
            "floor_level_mm": self.floor_level_mm,
            "profile_type": self.profile_type
        }


class VehicleProfilesDB:
    """База эталонов транспортных средств"""
    
    def __init__(self):
        self.profiles: Dict[str, VehicleProfile] = {}
        self._init_default_profiles()
    
    def _init_default_profiles(self):
        """Инициализация стандартных профилей"""
        
        # ============================================================
        # ⚠️ ВНИМАНИЕ! Это ТЕСТОВЫЕ профили для разработки!
        # Реальные размеры будут получены из калибровки.
        # ============================================================
        
        # 1. ТЕСТОВАЯ КОРОБКА (для разработки)
        # Реальные размеры: 60x40x60 см (ДxШxВ)
        # Используется только для тестирования алгоритмов
        self.add_profile(VehicleProfile(
            name="Тестовая коробка 60x40",
            vehicle_type="box",
            brand="TEST",
            model="BOX-60x40",
            length_m=0.6,      # 60 см
            width_m=0.4,       # 40 см
            height_m=0.6,      # 60 см
            empty_height_mm=0,
            points_range=(10, 80),
            spread_range=(50, 500),
            floor_level_mm=1650,
            profile_type="test"
        ))
        
        # 2. Калибровочная коробка (для настройки)
        self.add_profile(VehicleProfile(
            name="Калибровочная коробка",
            vehicle_type="box",
            brand="CALIB",
            model="BOX-CALIB",
            length_m=0.5,
            width_m=0.4,
            height_m=0.25,
            empty_height_mm=0,
            points_range=(10, 60),
            spread_range=(50, 400),
            floor_level_mm=1700,
            profile_type="calibration"
        ))
        
        # ============================================================
        # РЕАЛЬНЫЕ ПРОФИЛИ ТЕХНИКИ (для production)
        # ============================================================
        
        # 3. КАМАЗ 65115 (самосвал)
        self.add_profile(VehicleProfile(
            name="КАМАЗ 65115",
            vehicle_type="truck",
            brand="КАМАЗ",
            model="65115",
            length_m=6.0,
            width_m=2.5,
            height_m=2.0,
            empty_height_mm=300,  # высота бортов
            points_range=(100, 400),
            spread_range=(500, 2000),
            floor_level_mm=2000,
            profile_type="dump_truck"
        ))
        
        # 4. КАМАЗ 6520
        self.add_profile(VehicleProfile(
            name="КАМАЗ 6520",
            vehicle_type="truck",
            brand="КАМАЗ",
            model="6520",
            length_m=6.5,
            width_m=2.55,
            height_m=2.2,
            empty_height_mm=350,
            points_range=(120, 450),
            spread_range=(600, 2200),
            floor_level_mm=2000,
            profile_type="dump_truck"
        ))
        
        # 5. Урал 5557
        self.add_profile(VehicleProfile(
            name="Урал 5557",
            vehicle_type="truck",
            brand="Урал",
            model="5557",
            length_m=5.8,
            width_m=2.5,
            height_m=1.8,
            empty_height_mm=250,
            points_range=(100, 350),
            spread_range=(500, 1800),
            floor_level_mm=2000,
            profile_type="dump_truck"
        ))
        
        # 6. МАЗ 5516
        self.add_profile(VehicleProfile(
            name="МАЗ 5516",
            vehicle_type="truck",
            brand="МАЗ",
            model="5516",
            length_m=6.2,
            width_m=2.5,
            height_m=2.1,
            empty_height_mm=320,
            points_range=(110, 420),
            spread_range=(550, 2100),
            floor_level_mm=2000,
            profile_type="dump_truck"
        ))
        
        # 7. Прицеп-самосвал
        self.add_profile(VehicleProfile(
            name="Прицеп самосвальный",
            vehicle_type="trailer",
            brand="Trailer",
            model="2ПТС-4",
            length_m=7.0,
            width_m=2.5,
            height_m=2.3,
            empty_height_mm=400,
            points_range=(150, 500),
            spread_range=(700, 2500),
            floor_level_mm=2000,
            profile_type="trailer"
        ))
        
        # 8. Железнодорожный вагон
        self.add_profile(VehicleProfile(
            name="Вагон-самосвал",
            vehicle_type="wagon",
            brand="Railway",
            model="ВС-105",
            length_m=10.0,
            width_m=2.8,
            height_m=2.5,
            empty_height_mm=500,
            points_range=(200, 800),
            spread_range=(1000, 3000),
            floor_level_mm=2000,
            profile_type="wagon"
        ))
        
        logger.info(f"✅ Загружено {len(self.profiles)} профилей (включая тестовые)")
    
    def add_profile(self, profile: VehicleProfile):
        """Добавить профиль в базу"""
        self.profiles[profile.name] = profile
        logger.info(f"➕ Добавлен профиль: {profile.name}")
    
    def get_profile(self, name: str) -> Optional[VehicleProfile]:
        """Получить профиль по имени"""
        return self.profiles.get(name)
    
    def find_matching_profile(self, distances_mm: List[int]) -> Dict[str, Any]:
        """
        Найти наиболее подходящий профиль по данным сканирования
        """
        if not distances_mm:
            return {
                "profile": None,
                "confidence": 0,
                "reason": "Нет данных",
                "matches": []
            }
        
        points_count = len(distances_mm)
        spread = max(distances_mm) - min(distances_mm) if distances_mm else 0
        avg_height = sum(distances_mm) / len(distances_mm) if distances_mm else 0
        
        matches = []
        
        for name, profile in self.profiles.items():
            # Оценка совпадения по каждому параметру
            score = 0
            reasons = []
            
            # 1. Количество точек
            p_min, p_max = profile.points_range
            if p_min <= points_count <= p_max:
                score += 40
                reasons.append(f"точек {points_count} в диапазоне [{p_min}-{p_max}]")
            else:
                score -= 10
                reasons.append(f"точек {points_count} вне диапазона")
            
            # 2. Разброс расстояний
            s_min, s_max = profile.spread_range
            if s_min <= spread <= s_max:
                score += 30
                reasons.append(f"разброс {spread}мм в диапазоне [{s_min}-{s_max}]")
            else:
                score -= 10
            
            # 3. Средняя высота (для определения пустоты)
            if profile.empty_height_mm > 0:
                # Если средняя высота близка к высоте пустого кузова
                if abs(avg_height - profile.empty_height_mm) < 100:
                    score += 20
                    reasons.append("высота соответствует пустому кузову")
            
            matches.append({
                "name": name,
                "profile": profile,
                "score": score,
                "reasons": reasons,
                "vehicle_type": profile.vehicle_type
            })
        
        # Сортируем по баллам
        matches.sort(key=lambda x: x["score"], reverse=True)
        
        best_match = matches[0] if matches else None
        
        logger.info(f"🔍 Найдено совпадений: {len(matches)}, лучший: {best_match['name'] if best_match else 'нет'}")
        
        return {
            "profile": best_match["profile"] if best_match else None,
            "confidence": max(0, best_match["score"]) if best_match else 0,
            "reason": best_match["reasons"][0] if best_match and best_match["reasons"] else "нет совпадений",
            "matches": matches[:3]  # топ-3 совпадения
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


# Глобальный экземпляр базы
vehicle_profiles = VehicleProfilesDB()