from decimal import Decimal
from types import SimpleNamespace
from datetime import datetime, timezone

import pytest

from lab_models import LabVolumeUnit
from schemas.laboratory import CoalFractionCreate, MeasurementInput
from services.lab.calculations import average_density, calculate_density, normalize_volume


def test_experiment_lifecycle_in_database():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import models
    from schemas.laboratory import ExperimentCreate
    from services.lab.experiments import complete_experiment, create_experiment

    engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    grade = models.CoalGrade(code="D", name="Long flame")
    fraction = models.CoalFraction(name="0-50", min_size_mm=0, max_size_mm=50)
    supplier = models.Supplier(code="CUT", name="Test mine")
    db.add_all([grade, fraction, supplier]); db.commit()
    item = create_experiment(db, ExperimentCreate(experiment_number="LAB-1", coal_grade_id=grade.id,
        coal_fraction_id=fraction.id, supplier_id=supplier.id, tested_at=datetime.now(timezone.utc),
        laboratory_user_name="Tester", measurements=[MeasurementInput(sequence_number=1,
        entered_volume_value=10, entered_volume_unit=LabVolumeUnit.LITER, material_mass_kg=8.5)]))
    assert item.measurements[0].calculated_density_kg_m3 == Decimal("850.000000")
    assert complete_experiment(db, item).status == models.LabExperimentStatus.COMPLETED
    assert len(item.audit_entries) == 3


def test_liters_are_normalized_to_cubic_metres():
    assert normalize_volume(Decimal("10"), LabVolumeUnit.LITER) == Decimal("0.010000000")


def test_density_is_calculated_with_decimal_precision():
    assert calculate_density(Decimal("8.5"), Decimal("0.01")) == Decimal("850.000000")


def test_average_uses_only_included_measurements():
    rows = [SimpleNamespace(calculated_density_kg_m3=Decimal("800"), is_included=True),
            SimpleNamespace(calculated_density_kg_m3=Decimal("1000"), is_included=True),
            SimpleNamespace(calculated_density_kg_m3=Decimal("5000"), is_included=False)]
    assert average_density(rows) == Decimal("900.00")


def test_zero_volume_is_rejected():
    with pytest.raises(ValueError):
        normalize_volume(Decimal("0"), LabVolumeUnit.M3)


def test_excluded_measurement_requires_reason():
    with pytest.raises(ValueError):
        MeasurementInput(sequence_number=1, entered_volume_value=1,
            entered_volume_unit=LabVolumeUnit.LITER, material_mass_kg=1, is_included=False)


def test_fraction_range_is_validated():
    with pytest.raises(ValueError):
        CoalFractionCreate(name="bad", min_size_mm=20, max_size_mm=10)
