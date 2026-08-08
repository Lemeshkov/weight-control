from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

import lab_models as lm
from services.lab.fuel_quality_calculations import calculate_fuel_quality

INPUT_FIELDS = ("sample_date","sample_name","calorimeter","sa_percent","alpha","wa_percent","aa_percent",
    "wr_percent","hydrogen_input_percent","qb_a_1_kcal_kg","qb_a_2_kcal_kg","va_percent",
    "lab_technician_name","wagon_numbers","invoice_number","fuel_consumption_note")
CALC_FIELDS = ("sa_percent","alpha","wa_percent","aa_percent","wr_percent","hydrogen_input_percent",
    "qb_a_1_kcal_kg","qb_a_2_kcal_kg","va_percent")


def _json_value(value):
    if isinstance(value, (date, datetime)): return value.isoformat()
    if isinstance(value, Decimal): return str(value)
    if isinstance(value, lm.LabExperimentStatus): return value.value
    return value


def _inputs(item):
    return {key:_json_value(getattr(item,key)) for key in INPUT_FIELDS}


def calculation(item):
    if item.status != lm.LabExperimentStatus.DRAFT and item.calculation_snapshot:
        return item.calculation_snapshot
    return calculate_fuel_quality(**{key:Decimal(str(getattr(item,key))) for key in CALC_FIELDS})


def serialize(item):
    return {"id":item.id,**_inputs(item),"status":item.status.value,
        "calculated":{key:_json_value(value) for key,value in calculation(item).items()},
        "created_at":item.created_at,"updated_at":item.updated_at,"archived_at":item.archived_at}


def _audit(db, item, action, previous=None, new=None):
    db.add(lm.LabFuelQualityAuditLog(test_id=item.id,action=action,changed_by_user_id=item.updated_by,
        changed_by_name=item.lab_technician_name,previous_values=previous,new_values=new))


def create(db:Session, payload):
    item=lm.LabFuelQualityTest(**payload.model_dump())
    db.add(item);db.flush();_audit(db,item,"CREATE",new=_inputs(item));db.commit();db.refresh(item);return item


def get(db:Session,test_id:int):
    item=db.get(lm.LabFuelQualityTest,test_id)
    if not item: raise HTTPException(404,"Анализ топлива не найден")
    return item


def update(db:Session,item,payload):
    if item.status != lm.LabExperimentStatus.DRAFT: raise HTTPException(409,"Завершённый анализ доступен только для чтения")
    if payload.expected_updated_at:
        current=item.updated_at; expected=payload.expected_updated_at
        if current.tzinfo is None and expected.tzinfo is not None: expected=expected.replace(tzinfo=None)
        if current != expected: raise HTTPException(409,"Анализ был изменён другим пользователем")
    before=_inputs(item)
    for key,value in payload.model_dump(exclude={"expected_updated_at"}).items(): setattr(item,key,value)
    item.updated_at=datetime.now(timezone.utc); calculation(item)
    _audit(db,item,"UPDATE",before,_inputs(item));db.commit();db.refresh(item);return item


def complete(db:Session,item):
    if item.status != lm.LabExperimentStatus.DRAFT: raise HTTPException(409,"Завершить можно только черновик")
    values=calculation(item)
    item.calculation_snapshot={key:_json_value(value) for key,value in values.items()}
    item.status=lm.LabExperimentStatus.COMPLETED;item.updated_at=datetime.now(timezone.utc)
    _audit(db,item,"COMPLETE",{"status":"DRAFT"},{"status":"COMPLETED","calculation_snapshot":item.calculation_snapshot})
    db.commit();db.refresh(item);return item


def archive(db:Session,item):
    if item.status != lm.LabExperimentStatus.COMPLETED: raise HTTPException(409,"Архивировать можно только завершённый анализ")
    item.status=lm.LabExperimentStatus.ARCHIVED;item.archived_at=datetime.now(timezone.utc);item.updated_at=datetime.now(timezone.utc)
    _audit(db,item,"ARCHIVE",{"status":"COMPLETED"},{"status":"ARCHIVED"});db.commit();db.refresh(item);return item
