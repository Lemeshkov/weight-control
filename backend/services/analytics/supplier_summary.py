from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session, joinedload

import lab_models as lm
import models
from schemas.analytics import SupplierSummaryFilters, SupplierSummaryResponse, SupplierSummaryRow, SupplierSummaryTotals
from schemas.supplier_admin import normalize_registration_number


def build_supplier_summary(db: Session, date_from: date, date_to: date, supplier_id: int | None = None) -> SupplierSummaryResponse:
    start=datetime.combine(date_from,time.min);end=datetime.combine(date_to+timedelta(days=1),time.min)
    trips=(db.query(models.Trip).options(joinedload(models.Trip.vehicle),joinedload(models.Trip.entry_measurement),joinedload(models.Trip.exit_measurement)).filter(models.Trip.status==models.TripStatus.COMPLETED,models.Trip.exit_time>=start,models.Trip.exit_time<end).all())
    admin_vehicles={v.registration_number_normalized:v for v in db.query(lm.SupplierVehicle).options(joinedload(lm.SupplierVehicle.supplier_assignments).joinedload(lm.VehicleSupplierAssignment.supplier)).all()}
    totals=defaultdict(lambda:{"count":0,"weight":Decimal("0")})
    for trip in trips:
        if not trip.vehicle or not trip.exit_time:continue
        vehicle=admin_vehicles.get(normalize_registration_number(trip.vehicle.plate_number))
        if not vehicle:continue
        trip_date=trip.exit_time.date()
        assignment=next((a for a in vehicle.supplier_assignments if a.valid_from<=trip_date and (a.valid_to is None or a.valid_to>=trip_date)),None)
        if not assignment or (supplier_id is not None and assignment.supplier_id!=supplier_id):continue
        bucket=totals[(assignment.supplier_id,assignment.supplier.name)];bucket["count"]+=1
        if trip.entry_measurement is not None and trip.exit_measurement is not None:
            bucket["weight"]+=(Decimal(str(trip.entry_measurement.weight_brutto))-Decimal(str(trip.exit_measurement.weight_tare)))/Decimal("1000")
    rows=[SupplierSummaryRow(supplier_id=k[0],supplier_name=k[1],trip_count=v["count"],total_weight_t=v["weight"].quantize(Decimal("0.001"))) for k,v in sorted(totals.items(),key=lambda x:(x[0][1].casefold(),x[0][0]))]
    return SupplierSummaryResponse(filters=SupplierSummaryFilters(date_from=date_from,date_to=date_to,supplier_id=supplier_id),rows=rows,totals=SupplierSummaryTotals(trip_count=sum(x.trip_count for x in rows),total_weight_t=sum((x.total_weight_t for x in rows),Decimal("0.000"))))

# TODO: connect only a future authorized canonical production volume source here.
