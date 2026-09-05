from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

import lab_models as lm
import models
from database import get_db
from schemas.supplier_admin import *

router = APIRouter(prefix="/api/admin", tags=["supplier administration"])


def _commit(db):
    try: db.commit()
    except IntegrityError as exc:
        db.rollback(); raise HTTPException(409, "Запись с такими уникальными данными уже существует") from exc


def _page(query, page, page_size):
    total = query.count(); items = query.offset((page - 1) * page_size).limit(page_size).all()
    return items, {"total": total, "page": page, "page_size": page_size, "total_pages": (total + page_size - 1) // page_size}


def _supplier(db, item_id):
    item = db.get(lm.Supplier, item_id)
    if not item: raise HTTPException(404, "Поставщик не найден")
    return item


@router.get("/suppliers")
def suppliers(page: int=Query(1,ge=1), page_size: int=Query(20,ge=1,le=100), search: str|None=None, is_active: bool|None=None, db:Session=Depends(get_db)):
    q=db.query(lm.Supplier)
    if search: q=q.filter(or_(lm.Supplier.name.ilike(f"%{search.strip()}%"),lm.Supplier.short_name.ilike(f"%{search.strip()}%"),lm.Supplier.inn.ilike(f"%{search.strip()}%")))
    if is_active is not None:q=q.filter(lm.Supplier.is_active==is_active)
    rows,meta=_page(q.order_by(lm.Supplier.name.asc(),lm.Supplier.id.asc()),page,page_size)
    return {"items":[SupplierRead.model_validate(x) for x in rows],**meta}


@router.post("/suppliers",response_model=SupplierRead,status_code=201)
def create_supplier(data:SupplierCreate,db:Session=Depends(get_db)):
    if any(x.name.strip().casefold()==data.name.casefold() for x in db.query(lm.Supplier).all()):
        raise HTTPException(409,{"code":"SUPPLIER_ALREADY_EXISTS","message":f"Поставщик «{data.name}» уже существует."})
    item=lm.Supplier(**data.model_dump());db.add(item);_commit(db);db.refresh(item);return item


@router.get("/suppliers/{item_id}",response_model=SupplierRead)
def get_supplier(item_id:int,db:Session=Depends(get_db)):return _supplier(db,item_id)


@router.patch("/suppliers/{item_id}",response_model=SupplierRead)
def update_supplier(item_id:int,data:SupplierUpdate,db:Session=Depends(get_db)):
    item=_supplier(db,item_id)
    if data.name is not None and any(x.id!=item_id and x.name.strip().casefold()==data.name.casefold() for x in db.query(lm.Supplier).all()):
        raise HTTPException(409,{"code":"SUPPLIER_ALREADY_EXISTS","message":f"Поставщик «{data.name}» уже существует."})
    for key,value in data.model_dump(exclude_unset=True).items():setattr(item,key,value.strip() if key=="name" and value else value)
    _commit(db);db.refresh(item);return item


def _supplier_references(db,item_id):
    assignments=db.query(lm.VehicleSupplierAssignment).filter(lm.VehicleSupplierAssignment.supplier_id==item_id).count()
    return {
        "vehicles":db.query(func.count(func.distinct(lm.VehicleSupplierAssignment.vehicle_id))).filter(lm.VehicleSupplierAssignment.supplier_id==item_id).scalar() or 0,
        "vehicle_assignments":assignments,
        "coal_specs":db.query(lm.SupplierCoalSpec).filter(lm.SupplierCoalSpec.supplier_id==item_id).count(),
        "laboratory_records":db.query(lm.LabExperiment).filter(lm.LabExperiment.supplier_id==item_id).count(),
        "coal_acceptances":db.query(models.CoalAcceptance).filter(models.CoalAcceptance.supplier_id==item_id).count(),
    }


@router.delete("/suppliers/{item_id}",status_code=204)
def delete_supplier(item_id:int,db:Session=Depends(get_db)):
    item=_supplier(db,item_id);references=_supplier_references(db,item_id)
    if any(references.values()):
        raise HTTPException(409,{"code":"SUPPLIER_IN_USE","message":"Поставщик используется и не может быть удалён. Используйте деактивацию.","references":references})
    db.delete(item)
    try:db.commit()
    except IntegrityError as exc:
        db.rollback();raise HTTPException(409,{"code":"SUPPLIER_IN_USE","message":"Поставщик уже используется и не может быть удалён.","references":references}) from exc


def _current_assignment(vehicle):
    active=[x for x in vehicle.supplier_assignments if x.valid_to is None]
    return max(active,key=lambda x:(x.valid_from,x.id)) if active else None


def _vehicle_read(vehicle):
    current=_current_assignment(vehicle);data=VehicleRead.model_validate(vehicle).model_dump()
    data.update(current_supplier_id=current.supplier_id if current else None,current_supplier_name=current.supplier.name if current else None)
    return data


def _vehicle(db,item_id):
    item=db.query(lm.SupplierVehicle).options(joinedload(lm.SupplierVehicle.supplier_assignments).joinedload(lm.VehicleSupplierAssignment.supplier)).filter(lm.SupplierVehicle.id==item_id).first()
    if not item:raise HTTPException(404,"Машина не найдена")
    return item


@router.get("/vehicles")
def vehicles(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),search:str|None=None,supplier_id:int|None=None,is_active:bool|None=None,db:Session=Depends(get_db)):
    q=db.query(lm.SupplierVehicle).options(joinedload(lm.SupplierVehicle.supplier_assignments).joinedload(lm.VehicleSupplierAssignment.supplier))
    if search:
        p=f"%{normalize_registration_number(search)}%";q=q.filter(or_(lm.SupplierVehicle.registration_number_normalized.ilike(p),lm.SupplierVehicle.make_model.ilike(f"%{search.strip()}%")))
    if supplier_id:q=q.join(lm.VehicleSupplierAssignment).filter(lm.VehicleSupplierAssignment.supplier_id==supplier_id,lm.VehicleSupplierAssignment.valid_to.is_(None))
    if is_active is not None:q=q.filter(lm.SupplierVehicle.is_active==is_active)
    rows,meta=_page(q.order_by(lm.SupplierVehicle.registration_number_normalized.asc(),lm.SupplierVehicle.id.asc()),page,page_size)
    return {"items":[_vehicle_read(x) for x in rows],**meta}


@router.post("/vehicles",status_code=201)
def create_vehicle(data:VehicleCreate,db:Session=Depends(get_db)):
    _supplier(db,data.supplier_id);vehicle=lm.SupplierVehicle(registration_number=data.registration_number,registration_number_normalized=normalize_registration_number(data.registration_number),make_model=data.make_model,comment=data.comment)
    db.add(vehicle);db.flush();db.add(lm.VehicleSupplierAssignment(vehicle_id=vehicle.id,supplier_id=data.supplier_id,valid_from=data.valid_from,comment=data.comment));_commit(db);return _vehicle_read(_vehicle(db,vehicle.id))


@router.get("/vehicles/{item_id}")
def get_vehicle(item_id:int,db:Session=Depends(get_db)):return _vehicle_read(_vehicle(db,item_id))


@router.patch("/vehicles/{item_id}")
def update_vehicle(item_id:int,data:VehicleUpdate,db:Session=Depends(get_db)):
    item=_vehicle(db,item_id)
    for key,value in data.model_dump(exclude_unset=True).items():
        setattr(item,key,value.strip() if key=="registration_number" and value else value)
        if key=="registration_number":item.registration_number_normalized=normalize_registration_number(value)
    _commit(db);return _vehicle_read(item)


@router.delete("/vehicles/{item_id}",status_code=204)
def delete_vehicle(item_id:int,db:Session=Depends(get_db)):
    item=_vehicle(db,item_id);assignments=list(item.supplier_assignments)
    historical=sum(1 for x in assignments if x.valid_to is not None)
    references={"supplier_assignments":len(assignments),"historical_assignments":historical}
    # A freshly created unused duplicate has only its initial open assignment.
    # Closed/reassigned history is immutable business history.
    if historical or len(assignments)>1:
        raise HTTPException(409,{"code":"VEHICLE_IN_USE","message":"Машина имеет историю назначений и не может быть удалена.","references":references})
    try:
        for assignment in assignments:db.delete(assignment)
        db.flush();db.delete(item);db.commit()
    except IntegrityError as exc:
        db.rollback();raise HTTPException(409,{"code":"VEHICLE_IN_USE","message":"Машина используется и не может быть удалена.","references":references}) from exc


@router.get("/vehicles/{item_id}/supplier-history",response_model=list[AssignmentRead])
def assignment_history(item_id:int,db:Session=Depends(get_db)):return _vehicle(db,item_id).supplier_assignments


@router.post("/vehicles/{item_id}/reassign")
def reassign_vehicle(item_id:int,data:VehicleReassign,db:Session=Depends(get_db)):
    vehicle=_vehicle(db,item_id);_supplier(db,data.supplier_id);current=_current_assignment(vehicle)
    if current:
        if data.valid_from <= current.valid_from:raise HTTPException(422,"Новое назначение должно начинаться после текущего")
        current.valid_to=data.valid_from-timedelta(days=1)
    db.add(lm.VehicleSupplierAssignment(vehicle_id=vehicle.id,supplier_id=data.supplier_id,valid_from=data.valid_from,comment=data.comment));_commit(db);return _vehicle_read(_vehicle(db,item_id))


@router.get("/suppliers/{supplier_id}/vehicles")
def supplier_vehicles(supplier_id:int,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),db:Session=Depends(get_db)):
    return vehicles(page,page_size,None,supplier_id,None,db)


@router.get("/coal-grades")
def coal_grades(page:int=Query(1,ge=1),page_size:int=Query(100,ge=1,le=200),is_active:bool|None=None,db:Session=Depends(get_db)):
    q=db.query(lm.CoalGrade)
    if is_active is not None:q=q.filter(lm.CoalGrade.is_active==is_active)
    rows,meta=_page(q.order_by(lm.CoalGrade.name,lm.CoalGrade.id),page,page_size);return {"items":[CoalGradeRead.model_validate(x) for x in rows],**meta}


@router.post("/coal-grades",response_model=CoalGradeRead,status_code=201)
def create_grade(data:CoalGradeCreate,db:Session=Depends(get_db)):
    duplicate=next((x for x in db.query(lm.CoalGrade).all() if x.code.strip().casefold()==data.code.casefold() or x.name.strip().casefold()==data.name.casefold()),None)
    if duplicate:raise HTTPException(409,{"code":"COAL_GRADE_ALREADY_EXISTS","message":f"Марка угля «{data.code}» уже существует."})
    item=lm.CoalGrade(**data.model_dump());db.add(item);_commit(db);db.refresh(item);return item


@router.patch("/coal-grades/{item_id}",response_model=CoalGradeRead)
def update_grade(item_id:int,data:CoalGradeUpdate,db:Session=Depends(get_db)):
    item=db.get(lm.CoalGrade,item_id)
    if not item:raise HTTPException(404,"Марка угля не найдена")
    values=data.model_dump(exclude_unset=True)
    code=values.get("code",item.code);name=values.get("name",item.name)
    duplicate=next((x for x in db.query(lm.CoalGrade).filter(lm.CoalGrade.id!=item_id).all() if x.code.strip().casefold()==code.casefold() or x.name.strip().casefold()==name.casefold()),None)
    if duplicate:raise HTTPException(409,{"code":"COAL_GRADE_ALREADY_EXISTS","message":f"Марка угля «{code}» уже существует."})
    for k,v in values.items():setattr(item,k,v)
    _commit(db);db.refresh(item);return item


def _grade_references(db,item_id):
    return {"coal_specs":db.query(lm.SupplierCoalSpec).filter(lm.SupplierCoalSpec.coal_grade_id==item_id).count(),"laboratory_records":db.query(lm.LabExperiment).filter(lm.LabExperiment.coal_grade_id==item_id).count(),"coal_acceptances":db.query(models.CoalAcceptance).filter(models.CoalAcceptance.coal_grade_id==item_id).count()}


@router.delete("/coal-grades/{item_id}",status_code=204)
def delete_grade(item_id:int,db:Session=Depends(get_db)):
    item=db.get(lm.CoalGrade,item_id)
    if not item:raise HTTPException(404,"Марка угля не найдена")
    references=_grade_references(db,item_id)
    if any(references.values()):raise HTTPException(409,{"code":"COAL_GRADE_IN_USE","message":"Марка угля используется и не может быть удалена. Используйте деактивацию.","references":references})
    db.delete(item)
    try:db.commit()
    except IntegrityError as exc:
        db.rollback();raise HTTPException(409,{"code":"COAL_GRADE_IN_USE","message":"Марка угля уже используется и не может быть удалена.","references":references}) from exc


def _spec_read(item):
    data=CoalSpecRead.model_validate(item).model_dump();data.update(supplier_name=item.supplier.name,coal_grade_name=item.coal_grade.name);return data


def _spec(db,item_id):
    item=db.query(lm.SupplierCoalSpec).options(joinedload(lm.SupplierCoalSpec.supplier),joinedload(lm.SupplierCoalSpec.coal_grade),joinedload(lm.SupplierCoalSpec.fractions)).filter(lm.SupplierCoalSpec.id==item_id).first()
    if not item:raise HTTPException(404,"Спецификация не найдена")
    return item


def _ensure_spec_period_available(db,supplier_id,coal_grade_id,valid_from,valid_to,exclude_id=None):
    upper=valid_to or valid_from.max
    query=db.query(lm.SupplierCoalSpec).filter(lm.SupplierCoalSpec.supplier_id==supplier_id,lm.SupplierCoalSpec.coal_grade_id==coal_grade_id,lm.SupplierCoalSpec.valid_from<=upper,or_(lm.SupplierCoalSpec.valid_to.is_(None),lm.SupplierCoalSpec.valid_to>=valid_from))
    if exclude_id is not None:query=query.filter(lm.SupplierCoalSpec.id!=exclude_id)
    if query.first():raise HTTPException(409,{"code":"COAL_SPEC_PERIOD_CONFLICT","message":"Период спецификации пересекается с существующей версией."})


@router.get("/coal-specs")
def coal_specs(page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),supplier_id:int|None=None,coal_grade_id:int|None=None,is_active:bool|None=None,db:Session=Depends(get_db)):
    q=db.query(lm.SupplierCoalSpec).options(joinedload(lm.SupplierCoalSpec.supplier),joinedload(lm.SupplierCoalSpec.coal_grade),joinedload(lm.SupplierCoalSpec.fractions))
    if supplier_id:q=q.filter(lm.SupplierCoalSpec.supplier_id==supplier_id)
    if coal_grade_id:q=q.filter(lm.SupplierCoalSpec.coal_grade_id==coal_grade_id)
    if is_active is not None:q=q.filter(lm.SupplierCoalSpec.is_active==is_active)
    rows,meta=_page(q.order_by(lm.SupplierCoalSpec.supplier_id,lm.SupplierCoalSpec.coal_grade_id,lm.SupplierCoalSpec.valid_from.desc(),lm.SupplierCoalSpec.id.desc()),page,page_size)
    return {"items":[_spec_read(x) for x in rows],**meta}


@router.post("/coal-specs",status_code=201)
def create_spec(data:CoalSpecCreate,db:Session=Depends(get_db)):
    _supplier(db,data.supplier_id)
    if not db.get(lm.CoalGrade,data.coal_grade_id):raise HTTPException(422,"Марка угля не найдена")
    _ensure_spec_period_available(db,data.supplier_id,data.coal_grade_id,data.valid_from,data.valid_to)
    payload=data.model_dump(exclude={"fractions"});item=lm.SupplierCoalSpec(**payload);item.fractions=[lm.SupplierCoalFractionSpec(**x.model_dump()) for x in data.fractions];db.add(item);_commit(db);return _spec_read(_spec(db,item.id))


@router.get("/coal-specs/{item_id}")
def get_spec(item_id:int,db:Session=Depends(get_db)):return _spec_read(_spec(db,item_id))


@router.patch("/coal-specs/{item_id}")
def update_spec(item_id:int,data:CoalSpecUpdate,db:Session=Depends(get_db)):
    item=_spec(db,item_id)
    if item.valid_to is not None or not item.is_active:
        raise HTTPException(409,{"code":"COAL_SPEC_HISTORICAL_EDIT_FORBIDDEN","message":"Эта запись уже является исторической. Для изменения создайте новую версию."})
    values=data.model_dump(exclude_unset=True,exclude={"fractions"});supplier_id=values.get("supplier_id",item.supplier_id);grade_id=values.get("coal_grade_id",item.coal_grade_id)
    _supplier(db,supplier_id)
    if not db.get(lm.CoalGrade,grade_id):raise HTTPException(422,"Марка угля не найдена")
    valid_from=values.get("valid_from",item.valid_from);valid_to=values.get("valid_to",item.valid_to)
    if valid_to is not None and valid_to<valid_from:raise HTTPException(422,"Дата окончания не может быть раньше даты начала")
    _ensure_spec_period_available(db,supplier_id,grade_id,valid_from,valid_to,item_id)
    for key,value in values.items():setattr(item,key,value)
    if data.fractions is not None:item.fractions=[lm.SupplierCoalFractionSpec(**x.model_dump()) for x in data.fractions]
    _commit(db);return _spec_read(_spec(db,item_id))


@router.post("/coal-specs/{item_id}/replace",status_code=201)
def replace_spec(item_id:int,data:CoalSpecReplace,db:Session=Depends(get_db)):
    old=_spec(db,item_id)
    if data.supplier_id!=old.supplier_id or data.coal_grade_id!=old.coal_grade_id:raise HTTPException(422,"Версия должна сохранять поставщика и марку угля")
    if data.valid_from<=old.valid_from:raise HTTPException(422,"Новая версия должна начинаться позже предыдущей")
    old.valid_to=data.valid_from-timedelta(days=1);old.is_active=False
    return create_spec(data,db)


@router.delete("/coal-specs/{item_id}",status_code=204)
def delete_spec(item_id:int,db:Session=Depends(get_db)):
    item=_spec(db,item_id);references={"fraction_rules":len(item.fractions),"historical":int(item.valid_to is not None or not item.is_active)}
    if item.valid_to is not None or not item.is_active:
        raise HTTPException(409,{"code":"COAL_SPEC_IN_USE","message":"Историческая версия спецификации не может быть удалена.","references":references})
    try:db.delete(item);db.commit()
    except IntegrityError as exc:
        db.rollback();raise HTTPException(409,{"code":"COAL_SPEC_IN_USE","message":"Спецификация используется и не может быть удалена.","references":references}) from exc


@router.patch("/coal-specs/{item_id}/status")
def set_spec_status(item_id:int,is_active:bool,db:Session=Depends(get_db)):
    item=_spec(db,item_id);item.is_active=is_active;_commit(db);return _spec_read(item)


@router.get("/suppliers/{supplier_id}/coal-specs")
def supplier_specs(supplier_id:int,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),db:Session=Depends(get_db)):
    return coal_specs(page,page_size,supplier_id,None,None,db)
