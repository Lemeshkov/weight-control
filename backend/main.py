# # backend/main.py
# from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
# from fastapi.middleware.cors import CORSMiddleware
# from sqlalchemy.orm import Session
# from typing import List, Optional
# from datetime import datetime, date
# from pydantic import BaseModel
# import logging

# from database import get_db, engine
# import models
# from services.uniserver_client import uniserver_client
# from services.lidar_client import LidarClient
# from crud import TripCRUD, VehicleCRUD
# from config import settings
# from routers import weighing
# from routers import lidar
# from services.camera_client import CameraClient 
# from routers import lidar, scan_3d, camera, weighing
# from services.scale_monitor import scale_monitor
# import asyncio

# # Настройка логирования
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# # Создание таблиц при запуске (для разработки)
# models.Base.metadata.create_all(bind=engine)

# app = FastAPI(title="Weight Control System - Уголь-Контроль")

# # CORS настройки
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:8080"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # Подключаем роутеры
# app.include_router(weighing.router)
# app.include_router(lidar.router)
# app.include_router(scan_3d.router)
# app.include_router(camera.router)

# # Глобальный объект лидара
# # lidar_client = LidarClient(host="192.168.1.101", port=2111)

# # Pydantic модели для ответов
# class ScaleDataResponse(BaseModel):
#     state: str
#     state_desc: str
#     plate_number: str
#     weight: float
#     weight_type: str
#     is_stable: bool
#     weighing_time: str
#     doc_id: str

# class CurrentWeightResponse(BaseModel):
#     weight: float
#     unit: str
#     stable: bool
#     plate_number: Optional[str] = None
#     weight_type: Optional[str] = None
#     state: Optional[str] = None

# class TripResponse(BaseModel):
#     id: int
#     plate_number: str
#     entry_time: datetime
#     exit_time: Optional[datetime] = None
#     status: str
#     weight_brutto: Optional[float] = None
#     weight_tare: Optional[float] = None
#     net_weight: Optional[float] = None

# class StartWeighingResponse(BaseModel):
#     status: str
#     trip_id: Optional[int] = None
#     message: str
#     plate_number: Optional[str] = None
#     weight_brutto: Optional[float] = None

# class DailyStatsResponse(BaseModel):
#     date: str
#     completed_trips: int
#     total_weight_kg: float
#     total_weight_tons: float
#     average_weight_per_trip: Optional[float] = None

# # ============ Endpoints ============

# @app.get("/api/health")
# async def health_check():
#     return {"status": "ok", "timestamp": datetime.now().isoformat()}

# @app.get("/api/weight/current", response_model=CurrentWeightResponse)
# async def get_current_weight():
#     try:
#         data = await uniserver_client.get_current_weighting()
#         if not data:
#             return CurrentWeightResponse(weight=0, unit="kg", stable=False)
#         return CurrentWeightResponse(
#             weight=data['weight'],
#             unit="kg",
#             stable=data['is_stable'],
#             plate_number=data['plate_number'],
#             weight_type=data['weight_type'],
#             state=data['state']
#         )
#     except Exception as e:
#         logger.error(f"Error getting current weight: {e}")
#         return CurrentWeightResponse(weight=0, unit="kg", stable=False, state="error")

# @app.get("/api/scale/current", response_model=ScaleDataResponse)
# async def get_current_scale_data(db: Session = Depends(get_db)):
#     data = await uniserver_client.get_current_weighting()
#     if not data:
#         raise HTTPException(status_code=503, detail="Cannot connect to UniServer")
    
#     system_log = models.SystemLog(
#         device_type="scale",
#         event_type="info",
#         message=f"Scale data fetched: {data['weight']} kg, plate: {data['plate_number']}"
#     )
#     db.add(system_log)
#     db.commit()
    
#     return ScaleDataResponse(
#         state=data['state'],
#         state_desc=data['state_desc'],
#         plate_number=data['plate_number'],
#         weight=data['weight'],
#         weight_type=data['weight_type'],
#         is_stable=data['is_stable'],
#         weighing_time=data['weighing_time'],
#         doc_id=data['doc_id']
#     )

# @app.post("/api/weighing/start", response_model=StartWeighingResponse)
# async def start_weighing(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
#     data = await uniserver_client.get_current_weighting()
    
#     if not data:
#         raise HTTPException(status_code=503, detail="Cannot connect to UniServer")
#     if not data['is_stable']:
#         raise HTTPException(status_code=400, detail="Весы нестабильны")
#     if data['weight_type'] != "БРУТТО":
#         raise HTTPException(status_code=400, detail=f"Ожидается БРУТТО, получено {data['weight_type']}")
#     if data['weight'] == 0:
#         raise HTTPException(status_code=400, detail="Нулевой вес")
    
#     vehicle = VehicleCRUD.get_or_create_by_plate(db, data['plate_number'])
#     active_trip = TripCRUD.get_trip_by_vehicle_and_status(db, vehicle.id, models.TripStatus.ENTRY)
    
#     if active_trip:
#         raise HTTPException(status_code=400, detail=f"Активный рейс уже существует")
    
#     trip = await TripCRUD.create_from_weighing(db, data)
#     logger.info(f"Started new trip {trip.id} for vehicle {data['plate_number']}")
    
#     return StartWeighingResponse(
#         status="started",
#         trip_id=trip.id,
#         message=f"Рейс начат. Автомобиль: {data['plate_number']}, вес: {data['weight']} кг",
#         plate_number=data['plate_number'],
#         weight_brutto=data['weight']
#     )

# @app.post("/api/weighing/complete")
# async def complete_weighing(db: Session = Depends(get_db)):
#     data = await uniserver_client.get_current_weighting()
    
#     if not data:
#         raise HTTPException(status_code=503, detail="Cannot connect to UniServer")
#     if not data['is_stable']:
#         raise HTTPException(status_code=400, detail="Весы нестабильны")
#     if data['weight_type'] != "ТАРА":
#         raise HTTPException(status_code=400, detail=f"Ожидается ТАРА, получено {data['weight_type']}")
    
#     vehicle = VehicleCRUD.get_or_create_by_plate(db, data['plate_number'])
#     active_trip = TripCRUD.get_trip_by_vehicle_and_status(db, vehicle.id, models.TripStatus.ENTRY)
    
#     if not active_trip:
#         raise HTTPException(status_code=400, detail=f"Нет активного рейса")
    
#     trip = TripCRUD.update_exit_weighing(db, active_trip.id, data)
#     net_weight = None
#     if trip.entry_measurement and trip.exit_measurement:
#         net_weight = trip.entry_measurement.weight_brutto - trip.exit_measurement.weight_tare
    
#     return {
#         "status": "completed",
#         "trip_id": trip.id,
#         "message": f"Рейс завершен. Нетто: {net_weight} кг",
#         "plate_number": data['plate_number'],
#         "weight_tare": data['weight'],
#         "net_weight": net_weight
#     }

# @app.get("/api/trips/active", response_model=List[TripResponse])
# async def get_active_trips(db: Session = Depends(get_db)):
#     trips = db.query(models.Trip).filter(models.Trip.status == models.TripStatus.ENTRY).all()
#     result = []
#     for trip in trips:
#         result.append(TripResponse(
#             id=trip.id,
#             plate_number=trip.vehicle.plate_number,
#             entry_time=trip.entry_time,
#             exit_time=trip.exit_time,
#             status=trip.status.value,
#             weight_brutto=trip.entry_measurement.weight_brutto if trip.entry_measurement else None,
#             weight_tare=None,
#             net_weight=None
#         ))
#     return result

# @app.get("/api/trips/completed")
# async def get_completed_trips(limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
#     trips = db.query(models.Trip).filter(
#         models.Trip.status == models.TripStatus.COMPLETED
#     ).order_by(models.Trip.exit_time.desc()).offset(offset).limit(limit).all()
    
#     result = []
#     for trip in trips:
#         net_weight = None
#         if trip.entry_measurement and trip.exit_measurement:
#             net_weight = trip.entry_measurement.weight_brutto - trip.exit_measurement.weight_tare
#         result.append({
#             "id": trip.id,
#             "plate_number": trip.vehicle.plate_number,
#             "driver_name": trip.driver_name,
#             "entry_time": trip.entry_time.isoformat(),
#             "exit_time": trip.exit_time.isoformat() if trip.exit_time else None,
#             "weight_brutto": trip.entry_measurement.weight_brutto if trip.entry_measurement else None,
#             "weight_tare": trip.exit_measurement.weight_tare if trip.exit_measurement else None,
#             "net_weight": net_weight,
#             "density": trip.density_calculated
#         })
#     return result

# @app.get("/api/statistics/daily", response_model=DailyStatsResponse)
# async def get_daily_statistics(date_str: Optional[str] = None, db: Session = Depends(get_db)):
#     if date_str:
#         target_date = datetime.fromisoformat(date_str).date()
#     else:
#         target_date = datetime.now().date()
    
#     day_start = datetime(target_date.year, target_date.month, target_date.day)
#     day_end = datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59)
    
#     completed_trips = db.query(models.Trip).filter(
#         models.Trip.status == models.TripStatus.COMPLETED,
#         models.Trip.exit_time >= day_start,
#         models.Trip.exit_time <= day_end
#     ).all()
    
#     total_weight = 0
#     for trip in completed_trips:
#         if trip.entry_measurement and trip.exit_measurement:
#             total_weight += (trip.entry_measurement.weight_brutto - trip.exit_measurement.weight_tare)
    
#     avg_weight = total_weight / len(completed_trips) if completed_trips else None
    
#     return DailyStatsResponse(
#         date=target_date.isoformat(),
#         completed_trips=len(completed_trips),
#         total_weight_kg=total_weight,
#         total_weight_tons=total_weight / 1000,
#         average_weight_per_trip=avg_weight
#     )

# @app.get("/api/vehicles/search")
# async def search_vehicles(plate: str, db: Session = Depends(get_db)):
#     vehicle = db.query(models.Vehicle).filter(models.Vehicle.plate_number.ilike(f"%{plate}%")).first()
#     if not vehicle:
#         return {"found": False, "message": "Автомобиль не найден"}
    
#     recent_trips = db.query(models.Trip).filter(
#         models.Trip.vehicle_id == vehicle.id
#     ).order_by(models.Trip.entry_time.desc()).limit(5).all()
    
#     return {
#         "found": True,
#         "vehicle": {
#             "id": vehicle.id,
#             "plate_number": vehicle.plate_number,
#             "model": vehicle.model,
#             "carrier_name": vehicle.carrier.name if vehicle.carrier else None
#         },
#         "recent_trips": [
#             {
#                 "date": trip.entry_time.isoformat(),
#                 "net_weight": (trip.entry_measurement.weight_brutto - trip.exit_measurement.weight_tare) 
#                 if trip.entry_measurement and trip.exit_measurement else None
#             }
#             for trip in recent_trips if trip.entry_measurement and trip.exit_measurement
#         ]
#     }

# @app.on_event("startup")
# async def startup_event():
#     # global lidar_client
#     logger.info("=" * 50)
#     logger.info("Starting Weight Control System - Уголь-Контроль")
#     logger.info(f"UniServer URL: {settings.UNISERVER_URL}")
#     logger.info("=" * 50)
    
#     test_connection = await uniserver_client.get_scale_params()
#     if test_connection:
#         logger.info("✓ Connected to UniServer")
#     else:
#         logger.warning("✗ Failed to connect to UniServer")
    
#     # if lidar_client.connect():
#     #     logger.info(" Лидар подключен")
#     # else:
#     #     logger.warning(" Лидар не подключен")

# @app.on_event("shutdown")
# async def shutdown_event():
#     # global lidar_client
#     # if lidar_client:
#     #     lidar_client.disconnect()
#     logger.info("Shutting down")

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, date
from pydantic import BaseModel
import logging
import asyncio

from database import get_db, engine
import models
from services.uniserver_client import uniserver_client
from services.lidar_client import LidarClient
from services.camera_client import CameraClient
from services.scale_monitor import scale_monitor
from crud import TripCRUD, VehicleCRUD
from config import settings
from routers import weighing, lidar, scan_3d, camera

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создание таблиц при запуске (для разработки)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Weight Control System - Уголь-Контроль")

# CORS настройки
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роутеры
app.include_router(weighing.router)
app.include_router(lidar.router)
app.include_router(scan_3d.router)
app.include_router(camera.router)

# Глобальный объект лидара
# lidar_client = LidarClient(host="192.168.1.101", port=2111)

# ============ Pydantic модели ============

class ScaleDataResponse(BaseModel):
    state: str
    state_desc: str
    plate_number: str
    weight: float
    weight_type: str
    is_stable: bool
    weighing_time: str
    doc_id: str

class CurrentWeightResponse(BaseModel):
    weight: float
    unit: str
    stable: bool
    plate_number: Optional[str] = None
    weight_type: Optional[str] = None
    state: Optional[str] = None

class TripResponse(BaseModel):
    id: int
    plate_number: str
    entry_time: datetime
    exit_time: Optional[datetime] = None
    status: str
    weight_brutto: Optional[float] = None
    weight_tare: Optional[float] = None
    net_weight: Optional[float] = None

class StartWeighingResponse(BaseModel):
    status: str
    trip_id: Optional[int] = None
    message: str
    plate_number: Optional[str] = None
    weight_brutto: Optional[float] = None

class DailyStatsResponse(BaseModel):
    date: str
    completed_trips: int
    total_weight_kg: float
    total_weight_tons: float
    average_weight_per_trip: Optional[float] = None

# ============ Endpoints ============

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.get("/api/weight/current", response_model=CurrentWeightResponse)
async def get_current_weight():
    try:
        data = await uniserver_client.get_current_weighting()
        if not data:
            return CurrentWeightResponse(weight=0, unit="kg", stable=False)
        return CurrentWeightResponse(
            weight=data['weight'],
            unit="kg",
            stable=data['is_stable'],
            plate_number=data['plate_number'],
            weight_type=data['weight_type'],
            state=data['state']
        )
    except Exception as e:
        logger.error(f"Error getting current weight: {e}")
        return CurrentWeightResponse(weight=0, unit="kg", stable=False, state="error")

@app.get("/api/scale/current", response_model=ScaleDataResponse)
async def get_current_scale_data(db: Session = Depends(get_db)):
    data = await uniserver_client.get_current_weighting()
    if not data:
        raise HTTPException(status_code=503, detail="Cannot connect to UniServer")
    
    system_log = models.SystemLog(
        device_type="scale",
        event_type="info",
        message=f"Scale data fetched: {data['weight']} kg, plate: {data['plate_number']}"
    )
    db.add(system_log)
    db.commit()
    
    return ScaleDataResponse(
        state=data['state'],
        state_desc=data['state_desc'],
        plate_number=data['plate_number'],
        weight=data['weight'],
        weight_type=data['weight_type'],
        is_stable=data['is_stable'],
        weighing_time=data['weighing_time'],
        doc_id=data['doc_id']
    )

@app.post("/api/weighing/start", response_model=StartWeighingResponse)
async def start_weighing(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    data = await uniserver_client.get_current_weighting()
    
    if not data:
        raise HTTPException(status_code=503, detail="Cannot connect to UniServer")
    if not data['is_stable']:
        raise HTTPException(status_code=400, detail="Весы нестабильны")
    if data['weight_type'] != "БРУТТО":
        raise HTTPException(status_code=400, detail=f"Ожидается БРУТТО, получено {data['weight_type']}")
    if data['weight'] == 0:
        raise HTTPException(status_code=400, detail="Нулевой вес")
    
    vehicle = VehicleCRUD.get_or_create_by_plate(db, data['plate_number'])
    active_trip = TripCRUD.get_trip_by_vehicle_and_status(db, vehicle.id, models.TripStatus.ENTRY)
    
    if active_trip:
        raise HTTPException(status_code=400, detail=f"Активный рейс уже существует")
    
    trip = await TripCRUD.create_from_weighing(db, data)
    logger.info(f"Started new trip {trip.id} for vehicle {data['plate_number']}")
    
    return StartWeighingResponse(
        status="started",
        trip_id=trip.id,
        message=f"Рейс начат. Автомобиль: {data['plate_number']}, вес: {data['weight']} кг",
        plate_number=data['plate_number'],
        weight_brutto=data['weight']
    )

@app.post("/api/weighing/complete")
async def complete_weighing(db: Session = Depends(get_db)):
    data = await uniserver_client.get_current_weighting()
    
    if not data:
        raise HTTPException(status_code=503, detail="Cannot connect to UniServer")
    if not data['is_stable']:
        raise HTTPException(status_code=400, detail="Весы нестабильны")
    if data['weight_type'] != "ТАРА":
        raise HTTPException(status_code=400, detail=f"Ожидается ТАРА, получено {data['weight_type']}")
    
    vehicle = VehicleCRUD.get_or_create_by_plate(db, data['plate_number'])
    active_trip = TripCRUD.get_trip_by_vehicle_and_status(db, vehicle.id, models.TripStatus.ENTRY)
    
    if not active_trip:
        raise HTTPException(status_code=400, detail=f"Нет активного рейса")
    
    trip = TripCRUD.update_exit_weighing(db, active_trip.id, data)
    net_weight = None
    if trip.entry_measurement and trip.exit_measurement:
        net_weight = trip.entry_measurement.weight_brutto - trip.exit_measurement.weight_tare
    
    return {
        "status": "completed",
        "trip_id": trip.id,
        "message": f"Рейс завершен. Нетто: {net_weight} кг",
        "plate_number": data['plate_number'],
        "weight_tare": data['weight'],
        "net_weight": net_weight
    }

@app.get("/api/trips/active", response_model=List[TripResponse])
async def get_active_trips(db: Session = Depends(get_db)):
    trips = db.query(models.Trip).filter(models.Trip.status == models.TripStatus.ENTRY).all()
    result = []
    for trip in trips:
        result.append(TripResponse(
            id=trip.id,
            plate_number=trip.vehicle.plate_number,
            entry_time=trip.entry_time,
            exit_time=trip.exit_time,
            status=trip.status.value,
            weight_brutto=trip.entry_measurement.weight_brutto if trip.entry_measurement else None,
            weight_tare=None,
            net_weight=None
        ))
    return result

@app.get("/api/trips/completed")
async def get_completed_trips(limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    trips = db.query(models.Trip).filter(
        models.Trip.status == models.TripStatus.COMPLETED
    ).order_by(models.Trip.exit_time.desc()).offset(offset).limit(limit).all()
    
    result = []
    for trip in trips:
        net_weight = None
        if trip.entry_measurement and trip.exit_measurement:
            net_weight = trip.entry_measurement.weight_brutto - trip.exit_measurement.weight_tare
        result.append({
            "id": trip.id,
            "plate_number": trip.vehicle.plate_number,
            "driver_name": trip.driver_name,
            "entry_time": trip.entry_time.isoformat(),
            "exit_time": trip.exit_time.isoformat() if trip.exit_time else None,
            "weight_brutto": trip.entry_measurement.weight_brutto if trip.entry_measurement else None,
            "weight_tare": trip.exit_measurement.weight_tare if trip.exit_measurement else None,
            "net_weight": net_weight,
            "density": trip.density_calculated
        })
    return result

@app.get("/api/statistics/daily", response_model=DailyStatsResponse)
async def get_daily_statistics(date_str: Optional[str] = None, db: Session = Depends(get_db)):
    if date_str:
        target_date = datetime.fromisoformat(date_str).date()
    else:
        target_date = datetime.now().date()
    
    day_start = datetime(target_date.year, target_date.month, target_date.day)
    day_end = datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59)
    
    completed_trips = db.query(models.Trip).filter(
        models.Trip.status == models.TripStatus.COMPLETED,
        models.Trip.exit_time >= day_start,
        models.Trip.exit_time <= day_end
    ).all()
    
    total_weight = 0
    for trip in completed_trips:
        if trip.entry_measurement and trip.exit_measurement:
            total_weight += (trip.entry_measurement.weight_brutto - trip.exit_measurement.weight_tare)
    
    avg_weight = total_weight / len(completed_trips) if completed_trips else None
    
    return DailyStatsResponse(
        date=target_date.isoformat(),
        completed_trips=len(completed_trips),
        total_weight_kg=total_weight,
        total_weight_tons=total_weight / 1000,
        average_weight_per_trip=avg_weight
    )

@app.get("/api/vehicles/search")
async def search_vehicles(plate: str, db: Session = Depends(get_db)):
    vehicle = db.query(models.Vehicle).filter(models.Vehicle.plate_number.ilike(f"%{plate}%")).first()
    if not vehicle:
        return {"found": False, "message": "Автомобиль не найден"}
    
    recent_trips = db.query(models.Trip).filter(
        models.Trip.vehicle_id == vehicle.id
    ).order_by(models.Trip.entry_time.desc()).limit(5).all()
    
    return {
        "found": True,
        "vehicle": {
            "id": vehicle.id,
            "plate_number": vehicle.plate_number,
            "model": vehicle.model,
            "carrier_name": vehicle.carrier.name if vehicle.carrier else None
        },
        "recent_trips": [
            {
                "date": trip.entry_time.isoformat(),
                "net_weight": (trip.entry_measurement.weight_brutto - trip.exit_measurement.weight_tare) 
                if trip.entry_measurement and trip.exit_measurement else None
            }
            for trip in recent_trips if trip.entry_measurement and trip.exit_measurement
        ]
    }


# ============ События приложения ============

@app.on_event("startup")
async def startup_event():
    logger.info("=" * 50)
    logger.info("🚀 Starting Weight Control System - Уголь-Контроль")
    logger.info(f"   UniServer URL: {settings.UNISERVER_URL}")
    logger.info("=" * 50)
    
    # Проверяем подключение к UniServer
    test_connection = await uniserver_client.get_scale_params()
    if test_connection:
        logger.info("✅ Connected to UniServer")
    else:
        logger.warning("⚠️ Failed to connect to UniServer")
    
    # ✅ ЗАПУСКАЕМ МОНИТОРИНГ БЕЗ БЛОКИРОВКИ
    # asyncio.create_task(scale_monitor.start())
    # logger.info("🔄 Scale monitor started (checking every 2 seconds)")
    logger.info("ℹ️ Scale monitor is DISABLED for testing")


@app.on_event("shutdown")
async def shutdown_event():
    # Останавливаем мониторинг весов
    scale_monitor.stop()
    logger.info("⏹ Scale monitor stopped")
    
    # if lidar_client:
    #     lidar_client.disconnect()
    
    logger.info("=" * 50)
    logger.info("🛑 Weight Control System shutdown")
    logger.info("=" * 50)