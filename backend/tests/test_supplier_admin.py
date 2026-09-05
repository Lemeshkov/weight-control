from datetime import date

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
    yield TestClient(app)
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
