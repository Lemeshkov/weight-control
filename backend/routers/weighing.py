# backend/routers/weighing.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
import logging
from database import get_db
import models
from services.uniserver_client import uniserver_client
from services.lidar_profile_buffer import lidar_profile_buffer
from services.weighing_lidar_coordinator import weighing_lidar_coordinator
from crud import VehicleCRUD, TripCRUD

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/weighing", tags=["weighing"])


def commit_or_conflict(db: Session, message: str) -> None:
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(message)
        raise HTTPException(status_code=409, detail=message)


BRUTTO_TYPES = {"БРУТТО", "BRUTTO", "GROSS"}
TARE_TYPES = {"ТАРА", "TARE"}


def validate_weighing_payload(data: dict, allowed_types: set[str]) -> tuple[str, float, str]:
    if not data.get("is_stable", False):
        raise HTTPException(status_code=409, detail="Весы нестабильны")
    weight_type = str(data.get("weight_type") or "").strip().upper()
    if weight_type not in allowed_types:
        expected = "БРУТТО" if allowed_types == BRUTTO_TYPES else "ТАРА"
        raise HTTPException(status_code=409, detail=f"Ожидается {expected}, получено '{weight_type or 'пусто'}'")
    try:
        weight = float(data.get("weight", 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Некорректное значение веса")
    if weight <= 0:
        raise HTTPException(status_code=422, detail="Вес должен быть положительным")
    plate_number = str(data.get("plate_number") or "").strip().upper().replace(" ", "")
    if not plate_number:
        raise HTTPException(status_code=422, detail="Номер автомобиля отсутствует")
    return weight_type, weight, plate_number

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
    pass_token = weighing_lidar_coordinator.current_pass_token()
    
    if not data:
        raise HTTPException(status_code=503, detail="Cannot connect to UniServer")
    
    # Логируем данные
    logger.info(f"📊 Данные с весов: type={data.get('weight_type')}, weight={data.get('weight')}кг, stable={data.get('is_stable')}")
    
    # Проверяем стабильность
    if not data.get('is_stable', False):
        raise HTTPException(status_code=409, detail="Весы нестабильны")
    
    # Проверяем тип взвешивания
    weight_type, weight, plate_number = validate_weighing_payload(data, BRUTTO_TYPES)
    doc_id = data.get('doc_id', '')

    # ✅ Проверяем, есть ли уже рейс с таким uniserver_code (предотвращение дубликатов)
    if doc_id:
        existing_by_code = db.query(models.Trip).filter(
            models.Trip.uniserver_code == doc_id
        ).first()
        
        if existing_by_code:
            logger.warning(f"⚠️ Рейс с кодом {doc_id} уже существует (ID: {existing_by_code.id})")
            # Если рейс уже существует, но активный - возвращаем его
            if existing_by_code.status == models.TripStatus.ENTRY:
                await weighing_lidar_coordinator.bind_trip(existing_by_code.id, pass_token)
                return {
                    "trip_id": existing_by_code.id,
                    "message": f"Рейс уже существует для {plate_number}, вес {weight}кг",
                    "plate_number": plate_number,
                    "weight": weight,
                    "existing": True
                }
            else:
                # Если рейс завершен - создаем новый с другим кодом
                raise HTTPException(status_code=409, detail=f"Код взвешивания {doc_id} уже использован рейсом {existing_by_code.id}")
    
    # Получаем или создаем автомобиль
    vehicle = VehicleCRUD.get_or_create_by_plate(db, plate_number)
    
    # ✅ Создаем рейс с сохранением uniserver_code
    trip = models.Trip(
        vehicle_id=vehicle.id,
        entry_time=datetime.now(),
        status=models.TripStatus.ENTRY,
        uniserver_code=doc_id if doc_id else None  # ← Сохраняем уникальный код
    )
    db.add(trip)
    db.flush()
    
    # Создаем запись взвешивания (брутто)
    entry = models.EntryMeasurement(
        trip_id=trip.id,
        weight_brutto=weight
    )
    db.add(entry)
    
    # Сохраняем событие UniServer
    uniserver_event = models.UniserverEvent(
        trip_id=trip.id,
        uniserver_event_id=doc_id,
        plate_number=plate_number,
        weight=weight,
        raw_message=data.get("full_response", {})
    )
    db.add(uniserver_event)
    
    commit_or_conflict(db, "Не удалось создать рейс: конфликт данных")
    db.refresh(trip)
    await weighing_lidar_coordinator.bind_trip(trip.id, pass_token)
    
    logger.info(f"✅ Создан рейс {trip.id} для {plate_number}, вес {weight}кг, код: {doc_id}")
    
    return {
        "trip_id": trip.id,
        "message": f"Рейс начат для {plate_number}, вес {weight}кг",
        "plate_number": plate_number,
        "weight": weight,
        "uniserver_code": doc_id
    }



@router.post("/end-trip/{trip_id}")
async def end_trip(trip_id: int, db: Session = Depends(get_db)):
    """Завершить рейс (выезд)"""
    data = await uniserver_client.get_current_weighting()
    
    if not data:
        raise HTTPException(status_code=503, detail="Cannot connect to UniServer")
    
    _, weight, plate_number = validate_weighing_payload(data, TARE_TYPES)

    trip = db.query(models.Trip).filter(models.Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    # Проверяем, что рейс не завершен
    if trip.status != models.TripStatus.ENTRY:
        raise HTTPException(status_code=409, detail="Рейс не находится в статусе въезда")
    trip_plate = str(trip.vehicle.plate_number or "").strip().upper().replace(" ", "") if trip.vehicle else ""
    if trip_plate != plate_number:
        raise HTTPException(status_code=409, detail=f"На весах автомобиль {plate_number}, рейс принадлежит другому автомобилю")
    if not trip.entry_measurement:
        raise HTTPException(status_code=409, detail="У рейса отсутствует взвешивание БРУТТО")
    if trip.exit_measurement:
        raise HTTPException(status_code=409, detail="Взвешивание ТАРА уже существует")
    if weight >= trip.entry_measurement.weight_brutto:
        raise HTTPException(status_code=409, detail="ТАРА должна быть меньше БРУТТО")
    
    exit_measurement = models.ExitMeasurement(
        trip_id=trip.id,
        weight_tare=weight
    )
    db.add(exit_measurement)
    
    trip.exit_time = datetime.now()
    trip.status = models.TripStatus.COMPLETED
    commit_or_conflict(db, "Не удалось завершить рейс: конфликт данных")
    
    net_weight = trip.entry_measurement.weight_brutto - weight
    
    return {"net_weight": net_weight, "message": "Trip completed"}

@router.get("/trips", response_model=list[TripResponse])
async def get_trips(db: Session = Depends(get_db)):
    # Группируем по vehicle_id + entry_time (убираем дубликаты по времени)
    trips = db.query(models.Trip).distinct(
        models.Trip.vehicle_id,
        models.Trip.entry_time
    ).order_by(models.Trip.entry_time.desc()).limit(50).all()
    
    result = []
    for trip in trips:
        # Получаем вес брутто
        weight_brutto = None
        if trip.entry_measurement:
            weight_brutto = trip.entry_measurement.weight_brutto
        
        # Получаем вес тары
        weight_tare = None
        if trip.exit_measurement:
            weight_tare = trip.exit_measurement.weight_tare
        
        # Рассчитываем нетто
        net_weight = None
        if weight_brutto and weight_tare:
            net_weight = weight_brutto - weight_tare
        
        result.append(TripResponse(
            id=trip.id,
            plate_number=trip.vehicle.plate_number,
            entry_time=trip.entry_time,
            exit_time=trip.exit_time,
            status=trip.status.value,
            weight_brutto=weight_brutto,
            weight_tare=weight_tare,
            net_weight=net_weight
        ))
    
    return result

@router.get("/debug/scale-data")
async def debug_scale_data():
    """Отладочный эндпоинт для просмотра данных с весов"""
    data = await uniserver_client.get_current_weighting()
    
    if not data:
        return {"error": "Cannot connect to UniServer"}
    
    return {
        "plate_number": data.get('plate_number'),
        "weight": data.get('weight'),
        "weight_type": data.get('weight_type'),
        "weight_type_code": data.get('weight_type_code'),
        "is_stable": data.get('is_stable'),
        "state": data.get('state'),
        "state_desc": data.get('state_desc'),
        "brutto": data.get('brutto'),
        "tare": data.get('tare'),
        "netto": data.get('netto')
    }

@router.get("/history/uniserver")
async def get_uniserver_history(
    date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Получить историю взвешиваний из UniServer за день
    и синхронизировать с локальной БД
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    
    try:
        # Получаем историю из UniServer
        # (нужно уточнить API эндпоинт у поставщика)
        # Примерный запрос:
        history_data = await uniserver_client.get_history(date)
        
        if not history_data:
            return {"error": "No data from UniServer"}
        
        # Синхронизируем с локальной БД
        synced_count = 0
        for record in history_data:
            # Проверяем, есть ли уже такой рейс в БД
            existing = db.query(models.Trip).filter(
                models.Trip.id == record.get("id")
            ).first()
            
            if not existing:
                # Создаем новый рейс
                vehicle = VehicleCRUD.get_or_create_by_plate(
                    db, record.get("plate_number")
                )
                
                trip = models.Trip(
                    vehicle_id=vehicle.id,
                    entry_time=datetime.fromisoformat(record.get("entry_time")),
                    exit_time=datetime.fromisoformat(record.get("exit_time")) if record.get("exit_time") else None,
                    status=models.TripStatus.COMPLETED if record.get("exit_time") else models.TripStatus.ENTRY
                )
                db.add(trip)
                db.flush()
                
                # Добавляем измерения
                if record.get("weight_brutto"):
                    entry = models.EntryMeasurement(
                        trip_id=trip.id,
                        weight_brutto=record.get("weight_brutto")
                    )
                    db.add(entry)
                
                if record.get("weight_tare"):
                    exit_meas = models.ExitMeasurement(
                        trip_id=trip.id,
                        weight_tare=record.get("weight_tare")
                    )
                    db.add(exit_meas)
                
                synced_count += 1
        
        db.commit()
        
        # Возвращаем обновленную историю
        trips = db.query(models.Trip).order_by(
            models.Trip.entry_time.desc()
        ).limit(100).all()
        
        result = []
        for trip in trips:
            result.append({
                "id": trip.id,
                "plate_number": trip.vehicle.plate_number,
                "entry_time": trip.entry_time.isoformat(),
                "exit_time": trip.exit_time.isoformat() if trip.exit_time else None,
                "status": trip.status.value,
                "weight_brutto": trip.entry_measurement.weight_brutto if trip.entry_measurement else None,
                "weight_tare": trip.exit_measurement.weight_tare if trip.exit_measurement else None,
                "net_weight": (trip.entry_measurement.weight_brutto - trip.exit_measurement.weight_tare) 
                if trip.entry_measurement and trip.exit_measurement else None
            })
        
        return {
            "synced": synced_count,
            "total": len(result),
            "trips": result
        }
        
    except Exception as e:
        logger.error(f"Error syncing UniServer history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
@router.post("/auto-trip")
async def auto_create_trip(db: Session = Depends(get_db)):
    """
    Автоматическое создание рейса при взвешивании (для синхронизации с UniServer)
    Вызывается по Webhook или при опросе
    """
    # Получаем текущие данные с весов
    data = await uniserver_client.get_current_weighting()
    pass_token = weighing_lidar_coordinator.current_pass_token()
    
    if not data:
        raise HTTPException(status_code=503, detail="Cannot connect to UniServer")
    
    weight = data.get('weight', 0)
    plate_number = data.get('plate_number', '')
    weight_type = data.get('weight_type', '')
    is_stable = data.get('is_stable', False)
    
    # Проверяем, что есть вес и номер
    if weight <= 0 or not plate_number:
        return {"status": "ignore", "message": "Нет данных для создания рейса"}
    
    # Проверяем стабильность
    if not is_stable:
        return {"status": "waiting", "message": "Весы нестабильны, ждем..."}
    
    # Получаем или создаем автомобиль
    vehicle = VehicleCRUD.get_or_create_by_plate(db, plate_number)
    
    # Создаем новый рейс
    trip = models.Trip(
        vehicle_id=vehicle.id,
        entry_time=datetime.now(),
        status=models.TripStatus.ENTRY
    )
    db.add(trip)
    db.flush()
    
    # Создаем запись взвешивания
    entry = models.EntryMeasurement(
        trip_id=trip.id,
        weight_brutto=weight
    )
    db.add(entry)
    
    # Сохраняем событие UniServer
    uniserver_event = models.UniserverEvent(
        trip_id=trip.id,
        uniserver_event_id=data.get("doc_id", ""),
        plate_number=plate_number,
        weight=weight,
        raw_message=data.get("full_response", {})
    )
    db.add(uniserver_event)
    
    db.commit()
    await weighing_lidar_coordinator.bind_trip(trip.id, pass_token)
    
    logger.info(f" Автоматически создан рейс {trip.id} для {plate_number}, вес {weight} кг")
    
    return {
        "status": "created",
        "trip_id": trip.id,
        "plate_number": plate_number,
        "weight": weight,
        "message": f"Создан рейс для {plate_number}"
    }   

@router.post("/sync-measurement/{trip_id}")
async def sync_measurement(
    trip_id: int,
    db: Session = Depends(get_db)
):
    """
    Синхронизировать данные весов и лидара для рейса
    """
    trip = db.query(models.Trip).filter(models.Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    # Получаем текущие данные с весов
    scale_data = await uniserver_client.get_current_weighting()
    if not scale_data:
        raise HTTPException(status_code=503, detail="Cannot connect to UniServer")
    
    # Получаем данные с лидара
    from routers.lidar import lidar_client
    if not lidar_client.is_connected:
        raise HTTPException(status_code=503, detail="Лидар не подключен")
    
    scan_data = lidar_profile_buffer.latest_raw_data()
    parsed = lidar_client.parse_scan_data(scan_data, filter_angle=True, separate_object=True)
    
    # Рассчитываем объем
    distances_mm = parsed.get("distances_mm", [])
    if distances_mm:
        roadLevel = max(distances_mm) / 1000
        heights = []
        for d in distances_mm:
            distM = d / 1000
            if distM < roadLevel - 0.03:
                heights.append(roadLevel - distM)
            else:
                heights.append(0)
        
        validHeights = [h for h in heights if h > 0.01]
        if validHeights:
            avgHeight = sum(validHeights) / len(validHeights)
            volume_m3 = trip.vehicle.max_volume or 6.0 * 2.5 * avgHeight
            mass_tons = scale_data.get('weight', 0) / 1000
            density = mass_tons / volume_m3 if volume_m3 > 0 else 0
        else:
            volume_m3 = 0
            density = 0
    else:
        volume_m3 = 0
        density = 0
    
    # Сохраняем измерение лидара
    lidar_measurement = models.LidarMeasurement(
        trip_id=trip.id,
        timestamp=datetime.now(),
        points_count=parsed.get("points_count", 0),
        distances_mm=distances_mm,
        distances_m=[d/1000 for d in distances_mm],
        volume_m3=round(volume_m3, 3),
        mass_tons=round(scale_data.get('weight', 0) / 1000, 2),
        avg_height_m=round(avgHeight, 2) if validHeights else 0,
        cross_section_m2=round(avgHeight * 2.5, 3) if validHeights else 0,
        truck_length_m=trip.vehicle.max_volume and trip.vehicle.max_volume / 2.5 or 6.0,
        truck_width_m=2.5,
        coal_density_kg_m3=density * 1000 if density > 0 else 0,
        is_empty=parsed.get("is_empty", True)
    )
    db.add(lidar_measurement)
    
    # Обновляем рейс
    trip.density_calculated = round(density, 2)
    trip.exit_time = datetime.now()
    trip.status = models.TripStatus.COMPLETED
    
    db.commit()
    
    return {
        "trip_id": trip.id,
        "plate_number": trip.vehicle.plate_number,
        "weight_kg": scale_data.get('weight', 0),
        "volume_m3": volume_m3,
        "density_t_m3": density,
        "is_empty": parsed.get("is_empty", True)
    }

@router.get("/journal/history")
async def get_journal_history(
    days: int = 7,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    Получить историю взвешиваний из журнала UniServer за последние N дней
    """
    from datetime import datetime, timedelta
    
    # Вычисляем период
    date_to = datetime.now()
    date_from = date_to - timedelta(days=days)
    
    # Форматируем даты для UniServer
    date_from_str = date_from.strftime("%Y-%m-%dT00:00:00.000")
    date_to_str = date_to.strftime("%Y-%m-%dT23:59:59.999")
    
    logger.info(f"📋 Запрос журнала: с {date_from_str} по {date_to_str}")
    
    # Получаем записи из журнала
    records = await uniserver_client.get_journal_records(
        date_from=date_from_str,
        date_to=date_to_str,
        max_rows=limit
    )
    
    if not records:
        return {"status": "empty", "message": "Нет записей в журнале", "records": []}
    
    # Парсим записи
    parsed_records = []
    for record in records:
        parsed = uniserver_client.parse_journal_record(record)
        
        # Проверяем, есть ли уже такой рейс в локальной БД
        existing = db.query(models.Trip).join(models.EntryMeasurement).filter(
            models.EntryMeasurement.weight_brutto == parsed.get("weight_brutto"),
            models.Trip.entry_time >= date_from
        ).first()
        
        parsed["exists_locally"] = existing is not None
        parsed["local_trip_id"] = existing.id if existing else None
        
        parsed_records.append(parsed)
    
    return {
        "status": "success",
        "total": len(parsed_records),
        "period": {
            "from": date_from_str,
            "to": date_to_str
        },
        "records": parsed_records
    }

@router.post("/journal/sync")
async def sync_journal_history(
    days: int = 7,
    limit: int = 50,  # ←  ЛИМИТ
    db: Session = Depends(get_db)
):
    """Синхронизировать историю из журнала UniServer с локальной БД"""
    from datetime import datetime, timedelta
    
    date_to = datetime.now()
    date_from = date_to - timedelta(days=days)
    
    date_from_str = date_from.strftime("%Y-%m-%dT00:00:00.000")
    date_to_str = date_to.strftime("%Y-%m-%dT23:59:59.999")
    
    records = await uniserver_client.get_journal_records(
        date_from=date_from_str,
        date_to=date_to_str,
        max_rows=limit
    )
    
    if not records:
        return {"status": "empty", "message": "Нет записей в журнале"}
    
    synced = 0
    skipped = 0
    
    for record in records:
        try:
            parsed = uniserver_client.parse_journal_record(record)
            plate_number = parsed.get("plate_number")
            uniserver_code = parsed.get("code")  # ✅ Уникальный код из UniServer
            
            if not plate_number or not uniserver_code:
                db.commit()
                skipped += 1
                continue
            
            # ✅ ПРОВЕРКА ПО УНИКАЛЬНОМУ КОДУ - ОСНОВНОЙ МЕТОД
            existing = db.query(models.Trip).filter(
                models.Trip.uniserver_code == uniserver_code
            ).first()
            
            if existing:
                # Обновляем существующий рейс (если изменились данные)
                logger.info(f"🔄 Обновление рейса {existing.id} (code: {uniserver_code})")
                
                # Обновляем вес если изменился
                if parsed.get("weight_brutto", 0) > 0 and existing.entry_measurement:
                    existing.entry_measurement.weight_brutto = parsed.get("weight_brutto")
                
                if parsed.get("weight_tare", 0) > 0:
                    if existing.exit_measurement:
                        existing.exit_measurement.weight_tare = parsed.get("weight_tare")
                    else:
                        exit_meas = models.ExitMeasurement(
                            trip_id=existing.id,
                            weight_tare=parsed.get("weight_tare")
                        )
                        db.add(exit_meas)
                
                # Обновляем статус если появился exit_time
                if parsed.get("exit_time") and existing.status != models.TripStatus.COMPLETED:
                    existing.status = models.TripStatus.COMPLETED
                    try:
                        existing.exit_time = datetime.fromisoformat(parsed["exit_time"])
                    except:
                        existing.exit_time = datetime.now()
                
                skipped += 1
                continue
            
            # Создаем автомобиль
            vehicle = VehicleCRUD.get_or_create_by_plate(db, plate_number)
            
            # Парсим даты
            entry_time = None
            if parsed.get("entry_time"):
                try:
                    entry_time = datetime.fromisoformat(parsed["entry_time"])
                except:
                    entry_time = datetime.now()
            else:
                entry_time = datetime.now()
            
            # ✅ СОХРАНЯЕМ uniserver_code
            trip = models.Trip(
                vehicle_id=vehicle.id,
                entry_time=entry_time,
                status=models.TripStatus.COMPLETED,
                uniserver_code=uniserver_code  # ← УНИКАЛЬНЫЙ КЛЮЧ
            )
            db.add(trip)
            db.flush()
            
            # Добавляем брутто
            if parsed.get("weight_brutto", 0) > 0:
                entry = models.EntryMeasurement(
                    trip_id=trip.id,
                    weight_brutto=parsed.get("weight_brutto")
                )
                db.add(entry)
            
            # Добавляем тару
            if parsed.get("weight_tare", 0) > 0:
                exit_meas = models.ExitMeasurement(
                    trip_id=trip.id,
                    weight_tare=parsed.get("weight_tare")
                )
                db.add(exit_meas)
            
            db.commit()
            synced += 1
            logger.info(f"✅ Создан рейс {trip.id} для {plate_number} (code: {uniserver_code})")
            
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Ошибка синхронизации: {e}")
            skipped += 1
    
    return {
        "status": "success",
        "synced": synced,
        "skipped": skipped,
        "total": len(records)
    }
