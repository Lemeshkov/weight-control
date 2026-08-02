from decimal import Decimal, ROUND_HALF_UP

from lab_models import LabVolumeUnit

VOLUME_PRECISION = Decimal("0.000000001")
DENSITY_PRECISION = Decimal("0.000001")
DISPLAY_PRECISION = Decimal("0.01")


def normalize_volume(value: Decimal, unit: LabVolumeUnit) -> Decimal:
    if value <= 0:
        raise ValueError("Volume must be positive")
    result = value / Decimal("1000") if unit == LabVolumeUnit.LITER else value
    return result.quantize(VOLUME_PRECISION, rounding=ROUND_HALF_UP)


def calculate_density(mass_kg: Decimal, volume_m3: Decimal) -> Decimal:
    if mass_kg <= 0 or volume_m3 <= 0:
        raise ValueError("Mass and volume must be positive")
    return (mass_kg / volume_m3).quantize(DENSITY_PRECISION, rounding=ROUND_HALF_UP)


def average_density(measurements) -> Decimal | None:
    values = [Decimal(str(item.calculated_density_kg_m3)) for item in measurements if item.is_included]
    if not values:
        return None
    return (sum(values) / len(values)).quantize(DISPLAY_PRECISION, rounding=ROUND_HALF_UP)

