from datetime import date,datetime
from decimal import Decimal
from io import BytesIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base,get_db
import lab_models as lm
import models
from routers.analytics import router

def setup_client():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);Session=sessionmaker(bind=engine)
    app=FastAPI();app.include_router(router)
    def override():
        db=Session()
        try:yield db
        finally:db.close()
    app.dependency_overrides[get_db]=override
    return TestClient(app),Session,engine

def supplier_vehicle(db,name,plate,start,finish=None,active=True):
    s=lm.Supplier(name=name,is_active=active);v=lm.SupplierVehicle(registration_number=plate,registration_number_normalized=plate.replace(" ","").upper());db.add_all([s,v]);db.flush();db.add(lm.VehicleSupplierAssignment(vehicle_id=v.id,supplier_id=s.id,valid_from=start,valid_to=finish));db.commit();return s,v

def trip(db,plate,when,brutto=30000,tare=10000,status=models.TripStatus.COMPLETED):
    v=db.query(models.Vehicle).filter_by(plate_number=plate).first() or models.Vehicle(plate_number=plate);db.add(v);db.flush();t=models.Trip(vehicle_id=v.id,entry_time=when,exit_time=when,status=status);db.add(t);db.flush()
    if brutto is not None:db.add(models.EntryMeasurement(trip_id=t.id,weight_brutto=brutto))
    if tare is not None:db.add(models.ExitMeasurement(trip_id=t.id,weight_tare=tare))
    db.commit();return t

def test_summary_aggregation_filters_dates_nulls_and_totals():
    client,Session,engine=setup_client();db=Session();s1,_=supplier_vehicle(db,"Альфа","A 123 AA",date(2026,9,1));s2,_=supplier_vehicle(db,"Бета","B222BB",date(2026,9,1),active=False)
    trip(db,"a123aa",datetime(2026,9,1,10),30000,10000);trip(db,"A123AA",datetime(2026,9,5,23,59,59),31500,10000);trip(db,"B222BB",datetime(2026,9,3,12),25000,10000);trip(db,"A123AA",datetime(2026,9,6),30000,10000);trip(db,"A123AA",datetime(2026,9,4),30000,10000,models.TripStatus.REJECTED)
    response=client.get("/api/analytics/supplier-summary?date_from=2026-09-01&date_to=2026-09-05");assert response.status_code==200;body=response.json()
    assert [(r["supplier_name"],r["trip_count"],Decimal(r["total_weight_t"])) for r in body["rows"]]==[("Альфа",2,Decimal("41.500")),("Бета",1,Decimal("15.000"))]
    assert body["totals"]["trip_count"]==3 and Decimal(body["totals"]["total_weight_t"])==Decimal("56.500")
    assert all(r["total_volume_m3"] is None and r["bulk_density_t_m3"] is None for r in body["rows"])
    filtered=client.get(f"/api/analytics/supplier-summary?date_from=2026-09-01&date_to=2026-09-05&supplier_id={s2.id}").json();assert len(filtered["rows"])==1 and filtered["rows"][0]["supplier_id"]==s2.id
    assert client.get("/api/analytics/supplier-summary?date_from=2026-09-06&date_to=2026-09-05").status_code==422
    db.close();Base.metadata.drop_all(engine)

def test_historical_assignment_resolves_trip_supplier_without_join_multiplication():
    client,Session,engine=setup_client();db=Session();old,v=supplier_vehicle(db,"Старый","C333CC",date(2026,1,1),date(2026,6,30));new=lm.Supplier(name="Новый");db.add(new);db.flush();db.add(lm.VehicleSupplierAssignment(vehicle_id=v.id,supplier_id=new.id,valid_from=date(2026,7,1)));db.commit()
    trip(db,"C333CC",datetime(2026,6,30,20),20000,10000);trip(db,"C333CC",datetime(2026,7,1,8),22000,10000)
    rows=client.get("/api/analytics/supplier-summary?date_from=2026-06-01&date_to=2026-07-31").json()["rows"]
    assert [(r["supplier_name"],r["trip_count"]) for r in rows]==[("Новый",1),("Старый",1)]
    db.close();Base.metadata.drop_all(engine)

def test_excel_is_real_filtered_xlsx_with_numeric_weight_and_blank_future_values():
    client,Session,engine=setup_client();db=Session();s,_=supplier_vehicle(db,"Excel Поставщик","E444EE",date(2026,1,1));other,_=supplier_vehicle(db,"Другой","D555DD",date(2026,1,1));trip(db,"E444EE",datetime(2026,9,2),30500,10000);trip(db,"D555DD",datetime(2026,9,2),40000,10000)
    response=client.get(f"/api/analytics/supplier-summary/export?date_from=2026-09-01&date_to=2026-09-05&supplier_id={s.id}");assert response.status_code==200 and response.content[:2]==b"PK"
    sheet=load_workbook(BytesIO(response.content)).active;values=list(sheet.values);data=next(r for r in values if r[0]=="Excel Поставщик")
    assert isinstance(data[1],int) and isinstance(data[2],float) and data[3] is None and data[4] is None
    assert not any(r[0]=="Другой" for r in values if r[0])
    db.close();Base.metadata.drop_all(engine)
