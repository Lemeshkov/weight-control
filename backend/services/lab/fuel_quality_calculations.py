from decimal import Decimal, ROUND_HALF_UP

PERCENT_PRECISION = Decimal("0.01")
HEAT_PRECISION = Decimal("0.01")
SULFUR_HEAT_COEFFICIENT = Decimal("22.5")
HYDROGEN_HEAT_COEFFICIENT = Decimal("5.83")
HYDROGEN_CONVERSION_COEFFICIENT = Decimal("8.94")


def _round(value: Decimal, precision: Decimal) -> Decimal:
    return value.quantize(precision, rounding=ROUND_HALF_UP)


def calculate_fuel_quality(*, sa_percent: Decimal, alpha: Decimal, wa_percent: Decimal,
    aa_percent: Decimal, wr_percent: Decimal, hydrogen_input_percent: Decimal,
    qb_a_1_kcal_kg: Decimal, qb_a_2_kcal_kg: Decimal, va_percent: Decimal) -> dict[str, Decimal]:
    values = (sa_percent, wa_percent, aa_percent, wr_percent, hydrogen_input_percent, va_percent)
    if any(value < 0 or value >= 100 for value in values):
        raise ValueError("Процентные показатели должны быть в диапазоне от 0 до 100")
    if qb_a_1_kcal_kg <= 0 or qb_a_2_kcal_kg <= 0:
        raise ValueError("Показания калориметра должны быть больше нуля")
    analytical_dry = Decimal("100") - wa_percent
    combustible = Decimal("100") - wa_percent - aa_percent
    if analytical_dry <= 0 or combustible <= 0:
        raise ValueError("Некорректные Wa/Aa: знаменатель формулы должен быть больше нуля")

    qb_a = _round((qb_a_1_kcal_kg + qb_a_2_kcal_kg) / 2, HEAT_PRECISION)
    qs_a = _round(qb_a - (SULFUR_HEAT_COEFFICIENT * sa_percent + alpha * qb_a), HEAT_PRECISION)
    ad = _round(Decimal("100") * aa_percent / analytical_dry, PERCENT_PRECISION)
    ar_raw = aa_percent * (Decimal("100") - wr_percent) / analytical_dry
    ar = _round(ar_raw, PERCENT_PRECISION)
    if Decimal("100") - ar_raw <= 0:
        raise ValueError("Некорректная Ar: знаменатель формулы Wmax_daf должен быть больше нуля")
    vdaf = _round(va_percent * Decimal("100") / combustible, PERCENT_PRECISION)
    vr = _round(va_percent * (Decimal("100") - wr_percent) / analytical_dry, PERCENT_PRECISION)
    sr = _round(sa_percent * (Decimal("100") - wr_percent) / analytical_dry, PERCENT_PRECISION)
    sd = _round(sa_percent * Decimal("100") / analytical_dry, PERCENT_PRECISION)
    qs_daf = _round(qs_a * Decimal("100") / combustible, HEAT_PRECISION)
    qs_r = _round(qs_daf * (Decimal("100") - (wr_percent + ar_raw)) / Decimal("100"), HEAT_PRECISION)
    qi_a = _round(qs_a - HYDROGEN_HEAT_COEFFICIENT * (HYDROGEN_CONVERSION_COEFFICIENT * hydrogen_input_percent + wa_percent), HEAT_PRECISION)
    hr = _round(hydrogen_input_percent * (Decimal("100") - (wr_percent + ar_raw)) / Decimal("100"), PERCENT_PRECISION)
    qi_r = _round(qs_r - HYDROGEN_HEAT_COEFFICIENT * (wr_percent + HYDROGEN_CONVERSION_COEFFICIENT * hr), HEAT_PRECISION)
    wmax_daf_raw = wr_percent * Decimal("100") / (Decimal("100") - ar_raw)
    wmax_daf = _round(wmax_daf_raw, PERCENT_PRECISION)
    qs_af = _round(qs_daf * (Decimal("100") - wmax_daf_raw) / Decimal("100"), HEAT_PRECISION)
    qb_daf = _round(qb_a * Decimal("100") / combustible, HEAT_PRECISION)
    return {"qb_a_kcal_kg":qb_a,"qs_a_kcal_kg":qs_a,"ad_percent":ad,"ar_percent":ar,
        "vdaf_percent":vdaf,"vr_percent":vr,"sr_percent":sr,"sd_percent":sd,
        "qs_r_kcal_kg":qs_r,"qi_a_kcal_kg":qi_a,"hr_percent":hr,"qi_r_kcal_kg":qi_r,
        "qs_daf_kcal_kg":qs_daf,"wmax_daf_percent":wmax_daf,"qs_af_kcal_kg":qs_af,"qb_daf_kcal_kg":qb_daf}
