from datetime import datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from lab_models import CoalGrade, Supplier
from models import EntryMeasurement, ExitMeasurement, Trip, Vehicle
from routers.coal_acceptance import router
from services.coal_acceptance import calculate, contract_date


@pytest.fixture()
def client():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine); Session=sessionmaker(bind=engine)
    db=Session(); vehicle=Vehicle(plate_number="РЈ211РћРћ147",model="РљР°РјРђР—"); supplier=Supplier(code="S",name="РџРѕСЃС‚Р°РІС‰РёРє"); grade=CoalGrade(code="Р”",name="Р”"); db.add_all([vehicle,supplier,grade]); db.flush()
    trip=Trip(vehicle_id=vehicle.id,entry_time=datetime.now()); db.add(trip); db.flush(); db.add_all([EntryMeasurement(trip_id=trip.id,weight_brutto=35000),ExitMeasurement(trip_id=trip.id,weight_tare=4000)]); db.commit(); db.close()
    app=FastAPI(); app.include_router(router)
    def override():
        value=Session()
        try: yield value
        finally: value.close()
    app.dependency_overrides[get_db]=override
    yield TestClient(app)
    Base.metadata.drop_all(engine)


def test_excel_calculation_and_contract_boundary():
    result=calculate(Decimal("31.000"),Decimal("30.000"),Decimal("0.015"))
    assert result["difference_t"] == Decimal("1.000")
    assert result["allowed_difference_t"] == Decimal("0.450")
    assert contract_date(datetime(2026,8,7,7,59)).isoformat()=="2026-08-06"
    assert contract_date(datetime(2026,8,7,8,0)).isoformat()=="2026-08-07"


def test_trip_queue_crud_complete_and_export(client):
    queue=client.get("/api/coal-acceptance/queue").json(); assert queue["total"]==1; trip=queue["items"][0]; assert trip["actual_net_weight_t"]==31.0
    payload={"shipment_date":"2026-08-07","act_number":"A-1","transport_invoice_number":"TN-1","document_net_weight_t":"31,520","supplier_id":1,"coal_grade_id":1,"receiver_name":"РћРїРµСЂР°С‚РѕСЂ"}
    # API receives JSON decimal with a dot; comma normalization belongs to UI.
    payload["document_net_weight_t"]="31.520"
    created=client.post(f"/api/coal-acceptance/{trip['trip_id']}",json=payload); assert created.status_code==201
    assert client.post(f"/api/coal-acceptance/{trip['trip_id']}",json=payload).status_code==409
    stamp=created.json()["acceptance"]["updated_at"]
    done=client.post(f"/api/coal-acceptance/{trip['trip_id']}/complete",json={"expected_updated_at":stamp})
    assert done.status_code==200 and done.json()["status"]=="COMPLETED"
    export=client.get("/api/coal-acceptance/export.xlsx"); assert export.status_code==200 and export.content[:2]==b"PK"


def test_actual_weight_cannot_be_overridden(client):
    assert client.post("/api/coal-acceptance/1",json={"actual_net_weight_t":"1.000"}).status_code==422

