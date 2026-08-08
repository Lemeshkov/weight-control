from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

MASS_QUANTUM = Decimal("0.001")


def mass(value: Decimal | int | float | str | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(MASS_QUANTUM, rounding=ROUND_HALF_UP)


def actual_net_weight_t(trip) -> Decimal | None:
    if not trip.entry_measurement or not trip.exit_measurement:
        return None
    return mass((Decimal(str(trip.entry_measurement.weight_brutto)) - Decimal(str(trip.exit_measurement.weight_tare))) / 1000)


def calculate(actual: Decimal | None, document: Decimal | None, tolerance: Decimal) -> dict:
    if actual is None or document is None:
        return {key: None for key in ("difference_t", "allowed_difference_t", "shortage_t", "excess_t", "accepted_weight_t")}
    actual, document = mass(actual), mass(document)
    difference = mass(actual - document)
    allowed = mass(document * tolerance)
    absolute = abs(difference)
    shortage = mass(0 if difference >= 0 or absolute < allowed else absolute)
    excess = mass(absolute if difference >= 0 and absolute > allowed else 0)
    accepted = mass(document - shortage + excess)
    return {"difference_t": difference, "allowed_difference_t": allowed, "shortage_t": shortage, "excess_t": excess, "accepted_weight_t": accepted}


def acceptance_moment(trip) -> datetime:
    return trip.exit_time or trip.entry_time


def localized_moments(trip, local_timezone: str) -> tuple[datetime, datetime]:
    value = acceptance_moment(trip)
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo(local_timezone))
    local = value.astimezone(ZoneInfo(local_timezone))
    return local, local.astimezone(ZoneInfo("Europe/Moscow"))


def contract_date(local_datetime: datetime) -> date:
    boundary = datetime.combine(local_datetime.date(), time(8), tzinfo=local_datetime.tzinfo)
    return (local_datetime.date() if local_datetime >= boundary else local_datetime.date() - timedelta(days=1))

