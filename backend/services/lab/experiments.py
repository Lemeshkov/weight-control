import enum
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import lab_models as lm
from schemas.laboratory import ExperimentCreate, ExperimentUpdate, MeasurementInput, MeasurementUpdate
from services.lab.calculations import average_density, calculate_density, normalize_volume


def _json(data):
    if data is None:
        return None
    return {key: (value.isoformat() if isinstance(value, datetime) else value.value if isinstance(value, enum.Enum)
        else str(value) if isinstance(value, Decimal) else value) for key, value in data.items()}


def _audit(db, experiment, action, previous=None, new=None, measurement_id=None):
    db.add(lm.LabAuditLog(experiment_id=experiment.id, measurement_id=measurement_id, action=action,
        changed_by_user_id=experiment.laboratory_user_id, changed_by_name=experiment.laboratory_user_name,
        previous_values=_json(previous), new_values=_json(new)))


def _draft(experiment):
    if experiment.status != lm.LabExperimentStatus.DRAFT:
        raise HTTPException(409, "Only draft experiments can be edited")


def get_experiment(db: Session, experiment_id: int):
    item = db.get(lm.LabExperiment, experiment_id)
    if not item:
        raise HTTPException(404, "Experiment not found")
    return item


def add_measurement(db, experiment, data: MeasurementInput, audit=True):
    _draft(experiment)
    volume = normalize_volume(data.entered_volume_value, data.entered_volume_unit)
    item = lm.LabMeasurement(experiment=experiment, container_volume_m3=volume,
        calculated_density_kg_m3=calculate_density(data.material_mass_kg, volume), **data.model_dump())
    db.add(item)
    db.flush()
    if audit:
        _audit(db, experiment, "MEASUREMENT_ADDED", new=data.model_dump(), measurement_id=item.id)
    return item


def create_experiment(db: Session, data: ExperimentCreate):
    measurements = data.measurements
    item = lm.LabExperiment(**data.model_dump(exclude={"measurements"}))
    db.add(item)
    try:
        db.flush()
        _audit(db, item, "EXPERIMENT_CREATED", new=data.model_dump(exclude={"measurements"}))
        for measurement in measurements:
            add_measurement(db, item, measurement)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Experiment number or measurement sequence already exists") from exc
    db.refresh(item)
    return item


def update_experiment(db, item, data: ExperimentUpdate):
    _draft(item)
    changes = data.model_dump(exclude_unset=True)
    previous = {key: getattr(item, key) for key in changes}
    for key, value in changes.items():
        setattr(item, key, value)
    _audit(db, item, "EXPERIMENT_UPDATED", previous, changes)
    db.commit()
    db.refresh(item)
    return item


def update_measurement(db, item, data: MeasurementUpdate):
    experiment = item.experiment
    _draft(experiment)
    changes = data.model_dump(exclude_unset=True)
    previous = {key: getattr(item, key) for key in changes}
    for key, value in changes.items():
        setattr(item, key, value)
    if not item.is_included and not (item.exclusion_reason or "").strip():
        raise HTTPException(422, "exclusion_reason is required for excluded measurement")
    item.container_volume_m3 = normalize_volume(item.entered_volume_value, item.entered_volume_unit)
    item.calculated_density_kg_m3 = calculate_density(item.material_mass_kg, item.container_volume_m3)
    _audit(db, experiment, "MEASUREMENT_UPDATED", previous, changes, item.id)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Measurement sequence already exists") from exc
    db.refresh(item)
    return item


def delete_measurement(db, item):
    experiment = item.experiment
    _draft(experiment)
    previous = {"sequence_number": item.sequence_number, "density": item.calculated_density_kg_m3}
    _audit(db, experiment, "MEASUREMENT_DELETED", previous=previous, measurement_id=item.id)
    db.delete(item)
    db.commit()


def complete_experiment(db, item):
    _draft(item)
    if average_density(item.measurements) is None:
        raise HTTPException(422, "At least one included measurement is required")
    item.status = lm.LabExperimentStatus.COMPLETED
    _audit(db, item, "COMPLETED", {"status": "DRAFT"}, {"status": "COMPLETED"})
    db.commit(); db.refresh(item)
    return item


def archive_experiment(db, item):
    if item.status == lm.LabExperimentStatus.ARCHIVED:
        raise HTTPException(409, "Experiment is already archived")
    old = item.status.value
    item.status = lm.LabExperimentStatus.ARCHIVED
    item.archived_at = datetime.now(timezone.utc)
    _audit(db, item, "ARCHIVED", {"status": old}, {"status": "ARCHIVED"})
    db.commit(); db.refresh(item)
    return item


def serialize_experiment(item):
    included = [m for m in item.measurements if m.is_included]
    return {**item.__dict__, "measurements": item.measurements,
        "included_measurements_count": len(included), "average_density_kg_m3": average_density(item.measurements)}
