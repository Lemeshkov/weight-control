# backend/routers/weighing.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

from database import get_db
import models
from services.uniserver_client import uniserver_client

router = APIRouter(prefix="/api/weighing", tags=["weighing"])

# Pydantic модели для ответов
class CurrentWeightResponse(BaseModel):
    plate_number: str
    weight: float
    weight_type: str  # БРУТТО или ТАРА
    is_stable: bool
    state: str
    driver_name: Optional[str]
    timestamp: str

class TripResponse(BaseModel):
    id: int
    plate_number: str
    entry_time: datetime
    exit_time: Optional[datetime]
    status: str
    weight_brutto: Optional[float]
    weight_tare: Optional[float]
    net_weight: Optional[float]

@router.get("/current", response_model=CurrentWeightResponse)
async def get_current_weight():
    """Получить текущие данные с весов"""
    data = await uniserver_client.get_current_weighting()
    
    if not data:
        raise HTTPException(status_code=503, detail="Cannot connect to UniServer")
    
    return CurrentWeightResponse(
        plate_number=data['plate_number'],
        weight=data['weight'],
        weight_type=data['weight_type'],
        is_stable=data['is_stable'],
        state=data['state'],
        driver_name=data.get('driver_name'),
        timestamp=datetime.now().isoformat()
    )

@router.post("/start-trip")
async def start_trip(db: Session = Depends(get_db)):
    """Начать новый рейс (въезд)"""
    data = await uniserver_client.get_current_weighting()
    
    if not data:
        raise HTTPException(status_code=503, detail="Cannot connect to UniServer")
    
    if not data['is_stable']:
        raise HTTPException(status_code=400, detail="Scale not stable")
    
    if data['weight_type'] != "БРУТТО":
        raise HTTPException(status_code=400, detail="Expected BRUTTO weighing")
    
    # Создаем рейс
    vehicle = models.Vehicle(plate_number=data['plate_number'])
    db.add(vehicle)
    db.flush()
    
    trip = models.Trip(
        vehicle_id=vehicle.id,
        entry_time=datetime.now(),
        status=models.TripStatus.ENTRY
    )
    db.add(trip)
    db.flush()
    
    entry = models.EntryMeasurement(
        trip_id=trip.id,
        weight_brutto=data['weight']
    )
    db.add(entry)
    db.commit()
    
    return {"trip_id": trip.id, "message": "Trip started"}

@router.post("/end-trip/{trip_id}")
async def end_trip(trip_id: int, db: Session = Depends(get_db)):
    """Завершить рейс (выезд)"""
    data = await uniserver_client.get_current_weighting()
    
    if not data:
        raise HTTPException(status_code=503, detail="Cannot connect to UniServer")
    
    trip = db.query(models.Trip).filter(models.Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    exit_measurement = models.ExitMeasurement(
        trip_id=trip.id,
        weight_tare=data['weight']
    )
    db.add(exit_measurement)
    
    trip.exit_time = datetime.now()
    trip.status = models.TripStatus.COMPLETED
    db.commit()
    
    net_weight = trip.entry_measurement.weight_brutto - data['weight']
    
    return {"net_weight": net_weight, "message": "Trip completed"}

@router.get("/trips", response_model=list[TripResponse])
async def get_trips(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Получить список рейсов"""
    trips = db.query(models.Trip).order_by(
        models.Trip.entry_time.desc()
    ).offset(offset).limit(limit).all()
    
    result = []
    for trip in trips:
        result.append(TripResponse(
            id=trip.id,
            plate_number=trip.vehicle.plate_number,
            entry_time=trip.entry_time,
            exit_time=trip.exit_time,
            status=trip.status.value,
            weight_brutto=trip.entry_measurement.weight_brutto if trip.entry_measurement else None,
            weight_tare=trip.exit_measurement.weight_tare if trip.exit_measurement else None,
            net_weight=(trip.entry_measurement.weight_brutto - trip.exit_measurement.weight_tare) 
            if trip.entry_measurement and trip.exit_measurement else None
        ))
    
    return result