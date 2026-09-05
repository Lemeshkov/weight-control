from datetime import date,datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base,get_db
import models  # register shared production tables referenced by laboratory models
from routers.supplier_admin import router
from schemas.supplier_admin import FractionSpecInput,normalize_registration_number


@pytest.fixture()
def client():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);Session=sessionmaker(bind=engine)
    app=FastAPI();app.include_router(router)
    def override():
        db=Session()
        try:yield db
        finally:db.close()
    app.dependency_overrides[get_db]=override
    test_client=TestClient(app);test_client.app.state.Session=Session
    yield test_client
    Base.metadata.drop_all(engine)


def supplier(client,name="ООО Тест"):
    result=client.post("/api/admin/suppliers",json={"name":name,"inn":"4200000000"});assert result.status_code==201;return result.json()


def grade(client):
    result=client.post("/api/admin/coal-grades",json={"code":"Гр","name":"Газовый рядовой"});assert result.status_code==201;return result.json()


def test_supplier_crud_search_and_soft_deactivation(client):
    item=supplier(client);assert client.get(f"/api/admin/suppliers/{item['id']}").json()["name"]=="ООО Тест"
    changed=client.patch(f"/api/admin/suppliers/{item['id']}",json={"short_name":"Тест","is_active":False});assert changed.json()["is_active"] is False
    page=client.get("/api/admin/suppliers?search=Тест&is_active=false").json();assert page["total"]==1 and page["items"][0]["short_name"]=="Тест"


def test_vehicle_normalization_search_reassignment_and_history(client):
    first=supplier(client,"Первый");second=supplier(client,"Второй")
    result=client.post("/api/admin/vehicles",json={"registration_number":" а 123 вс 142 ","make_model":"КАМАЗ","supplier_id":first["id"],"valid_from":"2026-01-01"});assert result.status_code==201
    vehicle=result.json();assert vehicle["registration_number_normalized"]=="А123ВС142" and normalize_registration_number(" а 123 вс 142 ")=="А123ВС142"
    assert client.get("/api/admin/vehicles?search=а123").json()["total"]==1
    changed=client.post(f"/api/admin/vehicles/{vehicle['id']}/reassign",json={"supplier_id":second["id"],"valid_from":"2026-02-01"});assert changed.json()["current_supplier_id"]==second["id"]
    history=client.get(f"/api/admin/vehicles/{vehicle['id']}/supplier-history").json();assert len(history)==2 and history[0]["valid_to"]=="2026-01-31"


def test_grade_reused_and_can_be_deactivated(client):
    item=grade(client);changed=client.patch(f"/api/admin/coal-grades/{item['id']}",json={"is_active":False});assert changed.json()["is_active"] is False
    assert client.post("/api/admin/coal-grades",json={"code":"Гр","name":"Дубликат"}).status_code==409


def test_spec_fraction_validation_and_version_history(client):
    s=supplier(client);g=grade(client);payload={"supplier_id":s["id"],"coal_grade_id":g["id"],"calorific_value":"6000","calorific_value_unit":"kcal/kg","moisture_pct":"14","ash_pct":"16","valid_from":"2026-01-01","fractions":[{"fraction_min_mm":"0","fraction_max_mm":"5","operator":"<=","value":"40","unit":"%"},{"fraction_min_mm":"5","fraction_max_mm":"25","operator":">=","value":"50","unit":"%"}]}
    created=client.post("/api/admin/coal-specs",json=payload);assert created.status_code==201 and len(created.json()["fractions"])==2
    payload["valid_from"]="2026-03-01";payload["moisture_pct"]="15"
    replacement=client.post(f"/api/admin/coal-specs/{created.json()['id']}/replace",json=payload);assert replacement.status_code==201
    rows=client.get(f"/api/admin/coal-specs?supplier_id={s['id']}").json()["items"];assert len(rows)==2 and any(x["valid_to"]=="2026-02-28" for x in rows)
    with pytest.raises(ValueError):FractionSpecInput(fraction_min_mm=5,fraction_max_mm=1,operator="<=",value=40)
    assert client.post("/api/admin/coal-specs",json={**payload,"moisture_pct":101}).status_code==422


def test_pagination_empty_middle_last_and_stable_sort(client):
    assert client.get("/api/admin/suppliers?page=3&page_size=2").json()=={"items":[],"total":0,"page":3,"page_size":2,"total_pages":0}
    for name in ("В","А","Б","Г","Д"):supplier(client,name)
    pages=[client.get(f"/api/admin/suppliers?page={p}&page_size=2").json() for p in (1,2,3,4)]
    assert [x["name"] for x in pages[0]["items"]]==["А","Б"] and pages[1]["page"]==2 and len(pages[2]["items"])==1 and pages[3]["items"]==[]


def test_unused_supplier_delete_and_deactivation_remains(client):
    unused=supplier(client,"Новый");assert client.delete(f"/api/admin/suppliers/{unused['id']}").status_code==204
    assert client.get("/api/admin/suppliers?search=Новый").json()["total"]==0
    used=supplier(client,"Используется");client.post("/api/admin/vehicles",json={"registration_number":"Т001ЕСТ","supplier_id":used["id"],"valid_from":"2026-01-01"})
    blocked=client.delete(f"/api/admin/suppliers/{used['id']}");assert blocked.status_code==409 and blocked.json()["detail"]["code"]=="SUPPLIER_IN_USE"
    assert blocked.json()["detail"]["references"]["vehicle_assignments"]==1
    assert client.patch(f"/api/admin/suppliers/{used['id']}",json={"is_active":False}).json()["is_active"] is False


def test_supplier_with_spec_and_laboratory_history_cannot_be_deleted(client):
    s=supplier(client);g=grade(client)
    client.post("/api/admin/coal-specs",json={"supplier_id":s["id"],"coal_grade_id":g["id"],"valid_from":"2026-01-01","fractions":[]})
    blocked=client.delete(f"/api/admin/suppliers/{s['id']}");assert blocked.status_code==409 and blocked.json()["detail"]["references"]["coal_specs"]==1
    db=client.app.state.Session();fraction=models.CoalFraction(name="0-200");db.add(fraction);db.flush();db.add(models.LabExperiment(experiment_number="LAB-1",coal_grade_id=g["id"],coal_fraction_id=fraction.id,supplier_id=s["id"],tested_at=datetime.now(),laboratory_user_name="Лаборант"));db.commit();db.close()
    blocked=client.delete(f"/api/admin/suppliers/{s['id']}");assert blocked.json()["detail"]["references"]["laboratory_records"]==1


def test_coal_grade_full_lifecycle_duplicate_and_safe_delete(client):
    item=client.post("/api/admin/coal-grades",json={"code":" Д ","name":" Длиннопламенный "}).json();assert item["code"]=="Д"
    assert client.get("/api/admin/coal-grades?is_active=true").json()["total"]==1
    edited=client.patch(f"/api/admin/coal-grades/{item['id']}",json={"code":"ДР","description":"Описание","is_active":False}).json();assert edited["code"]=="ДР" and edited["is_active"] is False
    assert client.get("/api/admin/coal-grades?is_active=false").json()["items"][0]["id"]==item["id"]
    assert client.patch(f"/api/admin/coal-grades/{item['id']}",json={"is_active":True}).json()["is_active"] is True
    assert client.post("/api/admin/coal-grades",json={"code":" др ","name":"Другая"}).status_code==409
    assert client.delete(f"/api/admin/coal-grades/{item['id']}").status_code==204


def test_used_coal_grade_delete_is_blocked_and_historical_grade_readable(client):
    s=supplier(client);g=grade(client);client.post("/api/admin/coal-specs",json={"supplier_id":s["id"],"coal_grade_id":g["id"],"valid_from":"2026-01-01","fractions":[]})
    client.patch(f"/api/admin/coal-grades/{g['id']}",json={"is_active":False})
    assert client.get("/api/admin/coal-grades?is_active=false").json()["items"][0]["id"]==g["id"]
    blocked=client.delete(f"/api/admin/coal-grades/{g['id']}");assert blocked.status_code==409 and blocked.json()["detail"]["code"]=="COAL_GRADE_IN_USE"
    assert client.get("/api/admin/coal-specs").json()["items"][0]["coal_grade_name"]


def test_true_edit_preserves_supplier_vehicle_and_grade_ids_and_counts(client):
    s=supplier(client,"Поставщик");g=grade(client)
    vehicle=client.post("/api/admin/vehicles",json={"registration_number":"А123АА142","make_model":"КАМАЗ","supplier_id":s["id"],"valid_from":"2026-01-01"}).json()
    counts=(client.get("/api/admin/suppliers").json()["total"],client.get("/api/admin/vehicles").json()["total"],client.get("/api/admin/coal-grades").json()["total"])
    edited_s=client.patch(f"/api/admin/suppliers/{s['id']}",json={"name":"Поставщик Кузбасс"}).json()
    edited_v=client.patch(f"/api/admin/vehicles/{vehicle['id']}",json={"make_model":"КАМАЗ 6520"}).json()
    edited_g=client.patch(f"/api/admin/coal-grades/{g['id']}",json={"description":"Исправленное описание"}).json()
    assert (edited_s["id"],edited_v["id"],edited_g["id"])==(s["id"],vehicle["id"],g["id"])
    assert edited_v["make_model"]=="КАМАЗ 6520"
    assert counts==(client.get("/api/admin/suppliers").json()["total"],client.get("/api/admin/vehicles").json()["total"],client.get("/api/admin/coal-grades").json()["total"])


def test_vehicle_safe_delete_allows_fresh_duplicate_but_blocks_history(client):
    first=supplier(client,"Первый");second=supplier(client,"Второй")
    fresh=client.post("/api/admin/vehicles",json={"registration_number":"У001УУ142","supplier_id":first["id"],"valid_from":"2026-01-01"}).json()
    assert client.delete(f"/api/admin/vehicles/{fresh['id']}").status_code==204
    assert client.get(f"/api/admin/vehicles/{fresh['id']}").status_code==404
    used=client.post("/api/admin/vehicles",json={"registration_number":"У002УУ142","supplier_id":first["id"],"valid_from":"2026-01-01"}).json()
    client.post(f"/api/admin/vehicles/{used['id']}/reassign",json={"supplier_id":second["id"],"valid_from":"2026-02-01"})
    blocked=client.delete(f"/api/admin/vehicles/{used['id']}");assert blocked.status_code==409 and blocked.json()["detail"]["code"]=="VEHICLE_IN_USE"
    assert len(client.get(f"/api/admin/vehicles/{used['id']}/supplier-history").json())==2


def test_coal_spec_true_edit_and_explicit_version_have_distinct_semantics(client):
    s=supplier(client);g=grade(client);payload={"supplier_id":s["id"],"coal_grade_id":g["id"],"moisture_pct":"14","valid_from":"2026-01-01","fractions":[{"fraction_min_mm":0,"fraction_max_mm":5,"operator":"<=","value":40,"unit":"%"}]}
    original=client.post("/api/admin/coal-specs",json=payload).json();before=client.get("/api/admin/coal-specs").json()["total"]
    edited=client.patch(f"/api/admin/coal-specs/{original['id']}",json={"moisture_pct":"13.5"}).json()
    assert edited["id"]==original["id"] and float(edited["moisture_pct"])==13.5 and client.get("/api/admin/coal-specs").json()["total"]==before
    payload.update(valid_from="2026-03-01",moisture_pct="12")
    version=client.post(f"/api/admin/coal-specs/{original['id']}/replace",json=payload).json()
    assert version["id"]!=original["id"] and client.get("/api/admin/coal-specs").json()["total"]==before+1
    forbidden=client.patch(f"/api/admin/coal-specs/{original['id']}",json={"moisture_pct":"11"});assert forbidden.status_code==409 and forbidden.json()["detail"]["code"]=="COAL_SPEC_HISTORICAL_EDIT_FORBIDDEN"


def test_coal_spec_delete_current_allowed_historical_blocked(client):
    s=supplier(client);g=grade(client);base={"supplier_id":s["id"],"coal_grade_id":g["id"],"valid_from":"2026-01-01","fractions":[]}
    current=client.post("/api/admin/coal-specs",json=base).json();assert client.delete(f"/api/admin/coal-specs/{current['id']}").status_code==204
    old=client.post("/api/admin/coal-specs",json=base).json();base["valid_from"]="2026-02-01";client.post(f"/api/admin/coal-specs/{old['id']}/replace",json=base)
    blocked=client.delete(f"/api/admin/coal-specs/{old['id']}");assert blocked.status_code==409 and blocked.json()["detail"]["code"]=="COAL_SPEC_IN_USE"


def test_duplicate_updates_exclude_self_and_block_other_rows(client):
    first=supplier(client,"Первый");second=supplier(client,"Второй")
    assert client.patch(f"/api/admin/suppliers/{first['id']}",json={"name":" Первый "}).status_code==200
    assert client.patch(f"/api/admin/suppliers/{second['id']}",json={"name":"первый"}).status_code==409
    g1=grade(client);g2=client.post("/api/admin/coal-grades",json={"code":"Д","name":"Д"}).json()
    assert client.patch(f"/api/admin/coal-grades/{g1['id']}",json={"code":g1["code"]}).status_code==200
    assert client.patch(f"/api/admin/coal-grades/{g2['id']}",json={"code":g1["code"].lower()}).status_code==409
