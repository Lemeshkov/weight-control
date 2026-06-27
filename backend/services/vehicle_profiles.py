
# backend/services/vehicle_profiles.py

"""
База данных профилей транспортных средств и коробок
"""
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class VehicleProfile:
    """Профиль транспортного средства или коробки"""
    name: str
    vehicle_type: str  # "truck", "trailer", "wagon", "box"
    brand: Optional[str] = None
    model: Optional[str] = None
    length_m: float = 0
    width_m: float = 0
    height_m: float = 0
    empty_height_mm: float = 0
    points_range: Tuple[int, int] = (10, 500)
    spread_range: Tuple[int, int] = (50, 3000)
    box_type: str = "unknown"  # "small", "medium", "large", "unknown"

    # ⭐ НОВЫЕ ПОЛЯ ДЛЯ КОРОБОК
    min_points_for_filled: int = 1      # Минимум точек для "заполнено"
    max_points_for_empty: int = 3       # Максимум точек для "пусто"

    def to_dict(self) -> Dict[str, Any]:
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
            "box_type": self.box_type
        }

    def is_empty(self, height_mm: float, points_count: int) -> Tuple[bool, int]:
        """
        Определяет, пустой ли объект
        Использует ИНДИВИДУАЛЬНЫЕ ПОРОГИ для каждой коробки
        """
        if self.vehicle_type == "box":
            #  ЛОГИКА: используем индивидуальные пороги

            # Если есть явные пороги для этой коробки
            if self.min_points_for_filled > 0 and self.max_points_for_empty > 0:
                if points_count >= self.min_points_for_filled:
                    return False, 90  # Заполнено
                elif points_count <= self.max_points_for_empty:
                    return True, 90   # Пусто
                else:
                    # Промежуточная зона - смотрим на высоту
                    if height_mm > 80:
                        return False, 70  # Скорее заполнено
                    else:
                        return True, 70   # Скорее пусто

            # Старая логика (fallback)
            if height_mm < 50:
                return True, 90
            if points_count < 5:
                return True, 85
            return False, 80

        # Для грузовиков - старая логика
        if self.empty_height_mm > 0:
            diff = abs(height_mm - self.empty_height_mm)
            if diff < 100:
                return True, 90
            elif diff < 200:
                return True, 70
            else:
                return False, 80

        return height_mm < 200, 60

    def get_bounds(self, distances_mm: List[int], floor_level: int) -> Dict[str, Any]:
        """Возвращает границы объекта"""
        if not distances_mm:
            return {"error": "Нет данных"}

        min_dist = min(distances_mm)
        max_dist = max(distances_mm)
        center_dist = (min_dist + max_dist) / 2

        width_mm = self.width_m * 1000
        depth_mm = self.length_m * 1000
        height_mm = self.height_m * 1000

        return {
            "height": {
                "min": 30,
                "max": height_mm + 50,
                "from_floor": floor_level - min_dist if floor_level > min_dist else 0
            },
            "depth": {
                "min": center_dist - depth_mm / 2 - 50,
                "max": center_dist + depth_mm / 2 + 50,
                "center": center_dist
            },
            "spread": {
                "min": min_dist,
                "max": max_dist,
                "width": max_dist - min_dist
            },
            "profile": {
                "width_mm": width_mm,
                "depth_mm": depth_mm,
                "height_mm": height_mm
            }
        }

    def filter_points_inside(self, distances_mm: List[int], floor_level: int) -> List[int]:
        """Фильтрует точки, оставляя только те, что внутри объекта"""
        if not distances_mm or not self.width_m:
            return distances_mm

        width_mm = self.width_m * 1000
        depth_mm = self.length_m * 1000
        height_mm = self.height_m * 1000

        min_dist = min(distances_mm)
        max_dist = max(distances_mm)
        center_dist = (min_dist + max_dist) / 2

        min_height = 30
        max_height = height_mm + 50

        min_depth = center_dist - depth_mm / 2 - 50
        max_depth = center_dist + depth_mm / 2 + 50

        filtered = []
        for d in distances_mm:
            object_height = floor_level - d
            in_height = min_height <= object_height <= max_height
            in_depth = min_depth <= d <= max_depth

            if in_height and in_depth:
                filtered.append(d)

        return filtered


class VehicleProfiles:
    """База данных профилей"""

    def __init__(self):
        self.profiles: Dict[str, VehicleProfile] = {}
        self._init_default_profiles()

    def _init_default_profiles(self):
        """Инициализация стандартных профилей"""

        # ═══════════════════════════════════════════════════════════
        # КОРОБКИ
        # ═══════════════════════════════════════════════════════════

        # # S - Маленькая коробка
        # self.profiles["Коробка S (20x31x25)"] = VehicleProfile(
        #     name="Коробка S (20x31x25)",
        #     vehicle_type="box",
        #     brand="BOX",
        #     model="S-203125",
        #     length_m=0.31,   # 31 см
        #     width_m=0.20,    # 20 см
        #     height_m=0.25,   # 25 см
        #     empty_height_mm=50,
        #     points_range=(5, 15),
        #     spread_range=(30, 150),
        #     box_type="small",
        #     min_points_for_filled=8,   #  8+ точек = заполнено
        #     max_points_for_empty=3
        # )

        # M - Средняя коробка
        self.profiles["Коробка M (35x65x37)"] = VehicleProfile(
            name="Коробка M (35x65x37)",
            vehicle_type="box",
            brand="BOX",
            model="M-356537",
            length_m=0.65,   # 65 см
            width_m=0.35,    # 35 см
            height_m=0.37,   # 37 см
            empty_height_mm=50,
            points_range=(10, 22),
            spread_range=(100, 400),
            box_type="medium",
            min_points_for_filled=12,   #  8+ точек = заполнено
            max_points_for_empty=4      #  4- = пусто (3 точки = пусто)
        )

        # L - Большая коробка
        self.profiles["Коробка L (40x60x60)"] = VehicleProfile(
            name="Коробка L (40x60x60)",
            vehicle_type="box",
            brand="BOX",
            model="L-406060",
            length_m=0.60,   # 60 см
            width_m=0.40,    # 40 см
            height_m=0.60,   # 60 см
            empty_height_mm=50,
            points_range=(19, 25),
            spread_range=(200, 600),
            box_type="large",
            min_points_for_filled=18,   #  18+ точек = заполнено
            max_points_for_empty=5      #  5- = пусто (4 точки = пусто)
        )

        # ═══════════════════════════════════════════════════════════
        # ГРУЗОВИКИ
        # ═══════════════════════════════════════════════════════════

        self.profiles["КАМАЗ 65115"] = VehicleProfile(
            name="КАМАЗ 65115",
            vehicle_type="truck",
            brand="КАМАЗ",
            model="65115",
            length_m=7.0,
            width_m=2.5,
            height_m=1.8,
            empty_height_mm=300,
            points_range=(50, 200),
            spread_range=(500, 2000)
        )

        self.profiles["КАМАЗ 6520"] = VehicleProfile(
            name="КАМАЗ 6520",
            vehicle_type="truck",
            brand="КАМАЗ",
            model="6520",
            length_m=8.0,
            width_m=2.55,
            height_m=2.0,
            empty_height_mm=350,
            points_range=(60, 250),
            spread_range=(600, 2200)
        )

        self.profiles["Урал 5557"] = VehicleProfile(
            name="Урал 5557",
            vehicle_type="truck",
            brand="Урал",
            model="5557",
            length_m=6.5,
            width_m=2.5,
            height_m=1.7,
            empty_height_mm=280,
            points_range=(40, 180),
            spread_range=(500, 1800)
        )

        self.profiles["МАЗ 5516"] = VehicleProfile(
            name="МАЗ 5516",
            vehicle_type="truck",
            brand="МАЗ",
            model="5516",
            length_m=7.5,
            width_m=2.55,
            height_m=1.9,
            empty_height_mm=320,
            points_range=(50, 220),
            spread_range=(550, 2000)
        )

        self.profiles["Прицеп самосвальный"] = VehicleProfile(
            name="Прицеп самосвальный",
            vehicle_type="trailer",
            brand="TRAILER",
            model="DUMP",
            length_m=10.0,
            width_m=2.5,
            height_m=2.2,
            empty_height_mm=250,
            points_range=(80, 400),
            spread_range=(800, 2800)
        )

        self.profiles["Вагон-самосвал"] = VehicleProfile(
            name="Вагон-самосвал",
            vehicle_type="wagon",
            brand="WAGON",
            model="DUMP",
            length_m=12.0,
            width_m=2.8,
            height_m=2.5,
            empty_height_mm=300,
            points_range=(100, 500),
            spread_range=(1000, 3000)
        )

        logger.info(f"✅ Загружено {len(self.profiles)} профилей")

    def add_profile(self, profile: VehicleProfile):
        """Добавить профиль"""
        self.profiles[profile.name] = profile
        logger.info(f"✅ Добавлен профиль: {profile.name}")

    def get_profile(self, name: str) -> Optional[VehicleProfile]:
        """Получить профиль по имени"""
        return self.profiles.get(name)

    def get_all_profiles(self) -> List[Dict[str, Any]]:
        """Получить все профили в виде списка словарей"""
        return [p.to_dict() for p in self.profiles.values()]

    def find_matching_profile(self, distances_mm: List[int]) -> Dict[str, Any]:
        """
        Найти подходящий профиль по данным сканирования
        """
        if not distances_mm or len(distances_mm) < 5:
            return {"profile": None, "confidence": 0, "matches": []}

        points_count = len(distances_mm)
        spread = max(distances_mm) - min(distances_mm) if distances_mm else 0
        avg_dist = sum(distances_mm) / len(distances_mm) if distances_mm else 0

        matches = []

        for name, profile in self.profiles.items():
            score = 0

            # Проверка количества точек
            p_min, p_max = profile.points_range
            if p_min <= points_count <= p_max:
                # Чем ближе к центру, тем лучше
                center = (p_min + p_max) / 2
                if p_max - p_min > 0:
                    closeness = 1 - abs(points_count - center) / ((p_max - p_min) / 2)
                    closeness = max(0, min(1, closeness))
                else:
                    closeness = 1.0
                score += 30 * closeness
            else:
                # Штраф за несоответствие
                if points_count < p_min:
                    score -= 15 * (p_min - points_count) / p_min
                else:
                    score -= 15 * (points_count - p_max) / p_max

            # Проверка разброса
            s_min, s_max = profile.spread_range
            if s_min <= spread <= s_max:
                center = (s_min + s_max) / 2
                if s_max - s_min > 0:
                    closeness = 1 - abs(spread - center) / ((s_max - s_min) / 2)
                    closeness = max(0, min(1, closeness))
                else:
                    closeness = 1.0
                score += 30 * closeness
            else:
                if spread < s_min:
                    score -= 15 * (s_min - spread) / s_min
                else:
                    score -= 15 * (spread - s_max) / s_max

            # Бонус для коробок по типу
            if profile.vehicle_type == "box":
                if profile.box_type == "small" and points_count < 15:
                    score += 10
                elif profile.box_type == "medium" and 15 <= points_count <= 30:
                    score += 10
                elif profile.box_type == "large" and points_count > 30:
                    score += 10

            matches.append({
                "name": name,
                "profile": profile,
                "score": round(score, 1)
            })

        # Сортируем по убыванию
        matches.sort(key=lambda x: x["score"], reverse=True)

        best = matches[0] if matches else None

        # Уверенность: если лучший score > 50, считаем хорошим совпадением
        confidence = max(0, min(100, best["score"])) if best else 0

        return {
            "profile": best["profile"] if best else None,
            "confidence": confidence,
            "matches": matches[:3]
        }

    def get_box_info_from_profile(self, profile: Optional[VehicleProfile]) -> Dict[str, Any]:
        """
        Получить информацию о коробке из профиля
        """
        if not profile or profile.vehicle_type != "box":
            return {
                "box_type": "unknown",
                "box_label": "?",
                "box_name": "Неизвестная",
                "size_mm": {"width": 0, "depth": 0, "height": 0},
                "size_cm": {"width": 0, "depth": 0, "height": 0},
                "detected": False,
                "confidence": 0,
                "profile_name": None,
                "vehicle_type": "unknown"
            }

        width_m = profile.width_m
        depth_m = profile.length_m
        height_m = profile.height_m

        # Определяем тип коробки
        box_type_map = {
            "small": {"label": "S", "name": "Маленькая"},
            "medium": {"label": "M", "name": "Средняя"},
            "large": {"label": "L", "name": "Большая"},
        }

        box_info = box_type_map.get(profile.box_type, {"label": "?", "name": "Неизвестная"})

        return {
            "box_type": profile.box_type,
            "box_label": box_info["label"],
            "box_name": box_info["name"],
            "size_mm": {
                "width": int(width_m * 1000),
                "depth": int(depth_m * 1000),
                "height": int(height_m * 1000)
            },
            "size_cm": {
                "width": round(width_m * 100, 1),
                "depth": round(depth_m * 100, 1),
                "height": round(height_m * 100, 1)
            },
            "detected": True,
            "confidence": 85,
            "profile_name": profile.name,
            "vehicle_type": profile.vehicle_type
        }

    # ═══════════════════════════════════════════════════════════
    # ⭐ НОВЫЙ МЕТОД: ОПРЕДЕЛЕНИЕ ТИПА КОРОБКИ ПО ДАННЫМ
    # ═══════════════════════════════════════════════════════════

    def detect_box_type(self, distances_mm: List[int], floor_level: int) -> Dict[str, Any]:
        """
        Определяет тип коробки по данным сканирования

        Args:
            distances_mm: Список расстояний в мм
            floor_level: Уровень пола в мм

        Returns:
            Dict с информацией о коробке
        """
        if not distances_mm or len(distances_mm) < 3:
            return {
                "box_type": "unknown",
                "box_label": "?",
                "box_name": "Неизвестная",
                "confidence": 0,
                "size_mm": {"width": 0, "depth": 0, "height": 0},
                "size_cm": {"width": 0, "depth": 0, "height": 0},
                "detected": False,
                "reason": "Недостаточно данных"
            }

        # Вычисляем характеристики
        min_dist = min(distances_mm)
        max_dist = max(distances_mm)
        spread = max_dist - min_dist
        object_height = floor_level - min_dist if floor_level > min_dist else 0
        points_count = len(distances_mm)
        avg_dist = sum(distances_mm) / len(distances_mm)

        logger.info(f"📏 Анализ коробки: точек={points_count}, высота={object_height:.1f}мм, разброс={spread:.1f}мм")

        # ═══════════════════════════════════════════════════════════
        # ПРАВИЛА ОПРЕДЕЛЕНИЯ ТИПА КОРОБКИ
        # ═══════════════════════════════════════════════════════════

        # 1. По высоте (самый надежный признак)
        if object_height < 150:
            # Очень низкая - скорее всего пол или очень маленькая коробка
            if points_count < 10:
                return self._get_box_info("small", 60, "Низкая высота, мало точек")
            else:
                return self._get_box_info("small", 70, "Низкая высота")

        elif 150 <= object_height < 300:
            # S - Маленькая коробка
            if points_count < 15:
                return self._get_box_info("small", 85, "Высота 150-300мм, мало точек")
            else:
                # Если точек много, но высота маленькая - это может быть пол
                return self._get_box_info("small", 65, "Высота 150-300мм, много точек (возможно пол)")

        elif 300 <= object_height < 450:
            # M - Средняя коробка
            if 12 <= points_count <= 30:
                return self._get_box_info("medium", 90, "Высота 300-450мм, среднее кол-во точек")
            elif points_count < 12:
                return self._get_box_info("medium", 75, "Высота 300-450мм, мало точек")
            else:
                return self._get_box_info("medium", 70, "Высота 300-450мм, много точек")

        elif 450 <= object_height < 600:
            # Между M и L
            if points_count > 25:
                return self._get_box_info("large", 80, "Высота 450-600мм, много точек")
            else:
                return self._get_box_info("medium", 75, "Высота 450-600мм, мало точек")

        elif object_height >= 600:
            # L - Большая коробка
            if points_count > 20:
                return self._get_box_info("large", 90, "Высота >= 600мм, много точек")
            else:
                return self._get_box_info("large", 75, "Высота >= 600мм, мало точек")

        # 2. По количеству точек (если высота не определена)
        if points_count < 8:
            return self._get_box_info("small", 70, "Мало точек (<8)")
        elif points_count < 15:
            return self._get_box_info("small", 75, "Мало точек (<15)")
        elif points_count < 25:
            return self._get_box_info("medium", 80, "Среднее кол-во точек (15-25)")
        elif points_count < 40:
            return self._get_box_info("large", 80, "Много точек (25-40)")
        else:
            return self._get_box_info("large", 75, "Очень много точек (>40)")

    def _get_box_info(self, box_type: str, confidence: int, reason: str) -> Dict[str, Any]:
        """
        Вспомогательный метод для формирования информации о коробке
        """
        box_configs = {
            "small": {
                "label": "S",
                "name": "Маленькая",
                "size_mm": {"width": 200, "depth": 310, "height": 250},
                "size_cm": {"width": 20.0, "depth": 31.0, "height": 25.0},
                "profile_name": "Коробка S (20x31x25)"
            },
            "medium": {
                "label": "M",
                "name": "Средняя",
                "size_mm": {"width": 350, "depth": 650, "height": 370},
                "size_cm": {"width": 35.0, "depth": 65.0, "height": 37.0},
                "profile_name": "Коробка M (35x65x37)"
            },
            "large": {
                "label": "L",
                "name": "Большая",
                "size_mm": {"width": 400, "depth": 600, "height": 600},
                "size_cm": {"width": 40.0, "depth": 60.0, "height": 60.0},
                "profile_name": "Коробка L (40x60x60)"
            }
        }

        config = box_configs.get(box_type, box_configs["medium"])

        return {
            "box_type": box_type,
            "box_label": config["label"],
            "box_name": config["name"],
            "size_mm": config["size_mm"],
            "size_cm": config["size_cm"],
            "detected": True,
            "confidence": confidence,
            "profile_name": config["profile_name"],
            "vehicle_type": "box",
            "reason": reason
        }


# Глобальный экземпляр
vehicle_profiles = VehicleProfiles()