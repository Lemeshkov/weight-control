import csv
import io
import calendar
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import lab_models as lm
from database import get_db
from schemas.laboratory import *
from services.lab.calculations import average_density
from services.lab.experiments import *
from services.lab.fuel_quality import archive as archive_fuel_quality
from services.lab.fuel_quality import complete as complete_fuel_quality
from services.lab.fuel_quality import create as create_fuel_quality
from services.lab.fuel_quality import get as get_fuel_quality
from services.lab.fuel_quality import serialize as serialize_fuel_quality
from services.lab.fuel_quality import update as update_fuel_quality
from services.lab.fuel_quality_calculations import calculate_fuel_quality

router = APIRouter(prefix="/api/v1/laboratory", tags=["laboratory"])
RUSSIAN_MONTHS=("","январь","февраль","март","апрель","май","июнь","июль","август","сентябрь","октябрь","ноябрь","декабрь")


def _create_directory(db, model, data):
    item = model(**data.model_dump())
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback(); raise HTTPException(409, "Directory value already exists") from exc
    db.refresh(item); return item


@router.get("/coal-grades", response_model=list[CoalGradeRead])
def coal_grades(is_active: bool | None = True, db: Session = Depends(get_db)):
    query = db.query(lm.CoalGrade)
    return query.filter(lm.CoalGrade.is_active == is_active).all() if is_active is not None else query.all()


@router.post("/coal-grades", response_model=CoalGradeRead, status_code=201)
def create_coal_grade(data: CoalGradeCreate, db: Session = Depends(get_db)):
    return _create_directory(db, lm.CoalGrade, data)


@router.get("/coal-fractions", response_model=list[CoalFractionRead])
def coal_fractions(is_active: bool | None = True, db: Session = Depends(get_db)):
    query = db.query(lm.CoalFraction)
    return query.filter(lm.CoalFraction.is_active == is_active).all() if is_active is not None else query.all()


@router.post("/coal-fractions", response_model=CoalFractionRead, status_code=201)
def create_coal_fraction(data: CoalFractionCreate, db: Session = Depends(get_db)):
    return _create_directory(db, lm.CoalFraction, data)


@router.get("/suppliers", response_model=list[SupplierRead])
def suppliers(is_active: bool | None = True, db: Session = Depends(get_db)):
    query = db.query(lm.Supplier)
    return query.filter(lm.Supplier.is_active == is_active).all() if is_active is not None else query.all()


@router.post("/suppliers", response_model=SupplierRead, status_code=201)
def create_supplier(data: SupplierCreate, db: Session = Depends(get_db)):
    return _create_directory(db, lm.Supplier, data)


@router.post("/fuel-quality/calculate")
def fuel_quality_calculate(data: FuelQualityCalculateRequest):
    try: return calculate_fuel_quality(**data.model_dump())
    except ValueError as exc: raise HTTPException(422,str(exc)) from exc


@router.get("/fuel-quality")
def fuel_quality_list(date_from: date | None=None,date_to: date | None=None,month: int | None=Query(None,ge=1,le=12),
    year: int | None=None,status: lm.LabExperimentStatus | None=None,search: str | None=None,
    limit:int=Query(25,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db)):
    query=db.query(lm.LabFuelQualityTest)
    if year and month:
        date_from=date(year,month,1);date_to=date(year,month,calendar.monthrange(year,month)[1])
    if date_from: query=query.filter(lm.LabFuelQualityTest.sample_date>=date_from)
    if date_to: query=query.filter(lm.LabFuelQualityTest.sample_date<=date_to)
    if status: query=query.filter(lm.LabFuelQualityTest.status==status)
    if search:
        pattern=f"%{search}%";query=query.filter(or_(lm.LabFuelQualityTest.sample_name.ilike(pattern),lm.LabFuelQualityTest.invoice_number.ilike(pattern),lm.LabFuelQualityTest.wagon_numbers.ilike(pattern)))
    total=query.count();rows=query.order_by(lm.LabFuelQualityTest.sample_date.desc(),lm.LabFuelQualityTest.id.desc()).offset(offset).limit(limit).all()
    return {"items":[serialize_fuel_quality(x) for x in rows],"total":total,"limit":limit,"offset":offset}


@router.get("/fuel-quality/export.xlsx")
def fuel_quality_export(year:int=Query(...,ge=2000,le=2100),month:int=Query(...,ge=1,le=12),db:Session=Depends(get_db)):
    try: from openpyxl import load_workbook
    except ImportError as exc: raise HTTPException(503,"Excel export dependency is unavailable") from exc
    template=Path(__file__).resolve().parents[2]/"docs"/"reference"/"Ежесуточный контроль топлива 2026.xlsx"
    if not template.exists(): raise HTTPException(503,"Шаблон ежесуточного журнала не найден")
    workbook=load_workbook(template);sheet=workbook[f"{month:02d}"]
    for other in list(workbook.worksheets):
        if other is not sheet: workbook.remove(other)
    days=calendar.monthrange(year,month)[1]
    sheet["A1"] = f"Качество угля технологического контроля за {RUSSIAN_MONTHS[month]} {year} г."
    for row in range(3,34):
        if row-2<=days: sheet.cell(row,1).value=date(year,month,row-2)
        else: sheet.cell(row,1).value=None
        for column in range(2,14): sheet.cell(row,column).value=None
    rows=db.query(lm.LabFuelQualityTest).filter(lm.LabFuelQualityTest.sample_date>=date(year,month,1),
        lm.LabFuelQualityTest.sample_date<=date(year,month,days),lm.LabFuelQualityTest.status.in_([lm.LabExperimentStatus.COMPLETED,lm.LabExperimentStatus.ARCHIVED])).order_by(lm.LabFuelQualityTest.sample_date,lm.LabFuelQualityTest.id).all()
    for item in rows:
        values=serialize_fuel_quality(item)["calculated"];row=item.sample_date.day+2
        sheet.cell(row,1).value=item.sample_date
        mapped=[item.wr_percent,item.wa_percent,item.aa_percent,values["ar_percent"],values["ad_percent"],item.va_percent,
            values["vdaf_percent"],values["vr_percent"],item.sa_percent,values["sr_percent"],values["sd_percent"],round(float(values["qi_r_kcal_kg"]))]
        for column,value in enumerate(mapped,2): sheet.cell(row,column).value=float(value)
    output=io.BytesIO();workbook.save(output);output.seek(0)
    return StreamingResponse(output,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":f'attachment; filename="fuel-quality-{year}-{month:02d}.xlsx"'})


@router.post("/fuel-quality",status_code=201)
def fuel_quality_create(data:FuelQualityInput,db:Session=Depends(get_db)):
    try:return serialize_fuel_quality(create_fuel_quality(db,data))
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc


@router.get("/fuel-quality/{test_id}")
def fuel_quality_get(test_id:int,db:Session=Depends(get_db)):return serialize_fuel_quality(get_fuel_quality(db,test_id))


@router.put("/fuel-quality/{test_id}")
def fuel_quality_update(test_id:int,data:FuelQualityUpdate,db:Session=Depends(get_db)):
    try:return serialize_fuel_quality(update_fuel_quality(db,get_fuel_quality(db,test_id),data))
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc


@router.post("/fuel-quality/{test_id}/complete")
def fuel_quality_complete(test_id:int,db:Session=Depends(get_db)):return serialize_fuel_quality(complete_fuel_quality(db,get_fuel_quality(db,test_id)))


@router.post("/fuel-quality/{test_id}/archive")
def fuel_quality_archive(test_id:int,db:Session=Depends(get_db)):return serialize_fuel_quality(archive_fuel_quality(db,get_fuel_quality(db,test_id)))


@router.get("/fuel-quality/{test_id}/audit-log")
def fuel_quality_audit(test_id:int,db:Session=Depends(get_db)):
    get_fuel_quality(db,test_id);return db.query(lm.LabFuelQualityAuditLog).filter(lm.LabFuelQualityAuditLog.test_id==test_id).order_by(lm.LabFuelQualityAuditLog.created_at).all()


@router.post("/experiments", response_model=ExperimentRead, status_code=201)
def create(data: ExperimentCreate, db: Session = Depends(get_db)):
    return serialize_experiment(create_experiment(db, data))


@router.get("/experiments", response_model=ExperimentListResponse)
def experiments(date_from: datetime | None = None, date_to: datetime | None = None,
    coal_grade_id: int | None = None, supplier_id: int | None = None,
    status_filter: lm.LabExperimentStatus | None = Query(None, alias="status"), search: str | None = None,
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    query = db.query(lm.LabExperiment)
    if date_from: query = query.filter(lm.LabExperiment.tested_at >= date_from)
    if date_to: query = query.filter(lm.LabExperiment.tested_at <= date_to)
    if coal_grade_id: query = query.filter(lm.LabExperiment.coal_grade_id == coal_grade_id)
    if supplier_id: query = query.filter(lm.LabExperiment.supplier_id == supplier_id)
    if status_filter: query = query.filter(lm.LabExperiment.status == status_filter)
    if search:
        pattern = f"%{search}%"; query = query.filter(or_(lm.LabExperiment.experiment_number.ilike(pattern), lm.LabExperiment.batch_number.ilike(pattern), lm.LabExperiment.invoice_number.ilike(pattern)))
    total = query.count(); rows = query.order_by(lm.LabExperiment.tested_at.desc()).offset(offset).limit(limit).all()
    items = [ExperimentListItem(id=x.id, experiment_number=x.experiment_number, tested_at=x.tested_at, sampled_at=x.sampled_at,
        coal_grade=x.coal_grade.name, coal_fraction=x.coal_fraction.name, supplier=x.supplier.name,
        batch_number=x.batch_number, invoice_number=x.invoice_number, measurements_count=len(x.measurements),
        average_density_kg_m3=average_density(x.measurements), moisture_percent=x.moisture_percent,
        status=x.status, laboratory_user_name=x.laboratory_user_name) for x in rows]
    return ExperimentListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/experiments/export")
def export_experiments(db: Session = Depends(get_db)):
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["experiment_number", "tested_at", "coal_grade", "coal_fraction", "supplier",
        "batch_number", "invoice_number", "measurements_count", "average_density_kg_m3",
        "moisture_percent", "status", "laboratory_user_name"])
    rows = db.query(lm.LabExperiment).order_by(lm.LabExperiment.tested_at.desc()).all()
    for item in rows:
        writer.writerow([item.experiment_number, item.tested_at.isoformat(), item.coal_grade.name,
            item.coal_fraction.name, item.supplier.name, item.batch_number, item.invoice_number,
            len(item.measurements), average_density(item.measurements), item.moisture_percent,
            item.status.value, item.laboratory_user_name])
    content = "\ufeff" + output.getvalue()
    return StreamingResponse(iter([content]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=laboratory-experiments.csv"})


@router.get("/experiments/{experiment_id}", response_model=ExperimentRead)
def experiment(experiment_id: int, db: Session = Depends(get_db)):
    return serialize_experiment(get_experiment(db, experiment_id))


@router.patch("/experiments/{experiment_id}", response_model=ExperimentRead)
def patch_experiment(experiment_id: int, data: ExperimentUpdate, db: Session = Depends(get_db)):
    return serialize_experiment(update_experiment(db, get_experiment(db, experiment_id), data))


@router.post("/experiments/{experiment_id}/measurements", response_model=MeasurementRead, status_code=201)
def create_measurement(experiment_id: int, data: MeasurementInput, db: Session = Depends(get_db)):
    item = add_measurement(db, get_experiment(db, experiment_id), data)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback(); raise HTTPException(409, "Measurement sequence already exists") from exc
    db.refresh(item); return item


def _measurement(db, measurement_id):
    item = db.get(lm.LabMeasurement, measurement_id)
    if not item: raise HTTPException(404, "Measurement not found")
    return item


@router.patch("/measurements/{measurement_id}", response_model=MeasurementRead)
def patch_measurement(measurement_id: int, data: MeasurementUpdate, db: Session = Depends(get_db)):
    return update_measurement(db, _measurement(db, measurement_id), data)


@router.delete("/measurements/{measurement_id}", status_code=204)
def remove_measurement(measurement_id: int, db: Session = Depends(get_db)):
    delete_measurement(db, _measurement(db, measurement_id)); return Response(status_code=204)


@router.post("/experiments/{experiment_id}/complete", response_model=ExperimentRead)
def complete(experiment_id: int, db: Session = Depends(get_db)):
    return serialize_experiment(complete_experiment(db, get_experiment(db, experiment_id)))


@router.post("/experiments/{experiment_id}/archive", response_model=ExperimentRead)
def archive(experiment_id: int, db: Session = Depends(get_db)):
    return serialize_experiment(archive_experiment(db, get_experiment(db, experiment_id)))


@router.get("/experiments/{experiment_id}/audit-log", response_model=list[AuditRead])
def audit_log(experiment_id: int, db: Session = Depends(get_db)):
    get_experiment(db, experiment_id)
    return db.query(lm.LabAuditLog).filter(lm.LabAuditLog.experiment_id == experiment_id).order_by(lm.LabAuditLog.created_at).all()
