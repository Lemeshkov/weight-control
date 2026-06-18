# # app/crud.py - исправленная версия
# from sqlalchemy.orm import Session
# from sqlalchemy import and_
# from datetime import datetime
# from typing import Optional, List
# # Убираем app. из импортов
# import models
# from services.uniserver_client import uniserver_client

# class TripCRUD:
#     @staticmethod
#     def get_trip_by_vehicle_and_status(db: Session, vehicle_id: int, status: models.TripStatus) -> Optional[models.Trip]:
#         """Найти текущий рейс по автомобилю"""
#         return db.query(models.Trip).filter(
#             and_(
#                 models.Trip.vehicle_id == vehicle_id,
#                 models.Trip.status == status
#             )
#         ).first()
    
#     @staticmethod
#     async def create_from_weighing(db: Session, weighing_data: dict) -> models.Trip:
#         """Создать рейс из данных взвешивания"""
#         # Найти или создать автомобиль
#         vehicle = db.query(models.Vehicle).filter(
#             models.Vehicle.plate_number == weighing_data["plate_number"]
#         ).first()
        
#         if not vehicle:
#             # Автоматическое создание автомобиля при первом взвешивании
#             vehicle = models.Vehicle(
#                 plate_number=weighing_data["plate_number"],
#                 is_active=True
#             )
#             db.add(vehicle)
#             db.flush()
        
#         # Создать рейс
#         trip = models.Trip(
#             vehicle_id=vehicle.id,
#             entry_time=datetime.now(),
#             status=models.TripStatus.ENTRY
#         )
#         db.add(trip)
#         db.flush()
        
#         # Создать запись взвешивания (брутто на въезде)
#         if weighing_data["weight_type"] == "БРУТТО":
#             entry = models.EntryMeasurement(
#                 trip_id=trip.id,
#                 weight_brutto=weighing_data["weight"]
#             )
#             db.add(entry)
        
#         # Сохранить событие UniServer
#         uniserver_event = models.UniserverEvent(
#             trip_id=trip.id,
#             uniserver_event_id=weighing_data["doc_id"],
#             plate_number=weighing_data["plate_number"],
#             weight=weighing_data["weight"],
#             raw_message=weighing_data.get("full_response", {})
#         )
#         db.add(uniserver_event)
        
#         db.commit()
#         db.refresh(trip)
#         return trip
    
#     @staticmethod
#     def update_exit_weighing(db: Session, trip_id: int, weighing_data: dict) -> models.Trip:
#         """Обновить рейс данными выезда"""
#         trip = db.query(models.Trip).filter(models.Trip.id == trip_id).first()
#         if trip:
#             exit_measurement = db.query(models.ExitMeasurement).filter(
#                 models.ExitMeasurement.trip_id == trip_id
#             ).first()
            
#             if not exit_measurement:
#                 exit_measurement = models.ExitMeasurement(trip_id=trip_id)
#                 db.add(exit_measurement)
            
#             if weighing_data["weight_type"] == "ТАРА":
#                 exit_measurement.weight_tare = weighing_data["weight"]
                
#                 # Рассчитать вес нетто
#                 if trip.entry_measurement:
#                     net_weight = trip.entry_measurement.weight_brutto - weighing_data["weight"]
#                     # Сохранить net_weight, если нужно добавить поле
                
#                 trip.exit_time = datetime.now()
#                 trip.status = models.TripStatus.COMPLETED
            
#             db.commit()
#             db.refresh(trip)
        
#         return trip

# class VehicleCRUD:
#     @staticmethod
#     def get_or_create_by_plate(db: Session, plate_number: str) -> Vehicle:
#         """Получить или создать автомобиль по госномеру"""
#         # Нормализуем номер (убираем лишние пробелы)
#         plate_number = plate_number.strip()
        
#         # Ищем существующий автомобиль
#         vehicle = db.query(Vehicle).filter(Vehicle.plate_number == plate_number).first()
#         if vehicle:
#             logger.info(f"✅ Найден существующий автомобиль: {plate_number}")
#             return vehicle
        
#         # Если не найден - создаём новый
#         logger.info(f"🆕 Создаём новый автомобиль: {plate_number}")
#         vehicle = Vehicle(
#             plate_number=plate_number,
#             is_active=True,
#             created_at=datetime.utcnow()
#         )
#         db.add(vehicle)
#         db.flush()  # Не commit, чтобы можно было использовать в транзакции
#         return vehicle

# backend/crud.py - исправленная версия
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime
from typing import Optional, List
import logging
import models
from services.uniserver_client import uniserver_client

logger = logging.getLogger(__name__)

class TripCRUD:
    @staticmethod
    def get_trip_by_vehicle_and_status(db: Session, vehicle_id: int, status: models.TripStatus) -> Optional[models.Trip]:
        """Найти текущий рейс по автомобилю"""
        return db.query(models.Trip).filter(
            and_(
                models.Trip.vehicle_id == vehicle_id,
                models.Trip.status == status
            )
        ).first()
    
    @staticmethod
    async def create_from_weighing(db: Session, weighing_data: dict) -> models.Trip:
        """Создать рейс из данных взвешивания"""
        # Найти или создать автомобиль
        vehicle = db.query(models.Vehicle).filter(
            models.Vehicle.plate_number == weighing_data["plate_number"]
        ).first()
        
        if not vehicle:
            # Автоматическое создание автомобиля при первом взвешивании
            vehicle = models.Vehicle(
                plate_number=weighing_data["plate_number"],
                is_active=True
            )
            db.add(vehicle)
            db.flush()
        
        # Создать рейс
        trip = models.Trip(
            vehicle_id=vehicle.id,
            entry_time=datetime.now(),
            status=models.TripStatus.ENTRY
        )
        db.add(trip)
        db.flush()
        
        # Создать запись взвешивания (брутто на въезде)
        if weighing_data["weight_type"] == "БРУТТО":
            entry = models.EntryMeasurement(
                trip_id=trip.id,
                weight_brutto=weighing_data["weight"]
            )
            db.add(entry)
        
        # Сохранить событие UniServer
        uniserver_event = models.UniserverEvent(
            trip_id=trip.id,
            uniserver_event_id=weighing_data.get("doc_id", ""),
            plate_number=weighing_data["plate_number"],
            weight=weighing_data["weight"],
            raw_message=weighing_data.get("full_response", {})
        )
        db.add(uniserver_event)
        
        db.commit()
        db.refresh(trip)
        return trip
    
    @staticmethod
    def update_exit_weighing(db: Session, trip_id: int, weighing_data: dict) -> models.Trip:
        """Обновить рейс данными выезда"""
        trip = db.query(models.Trip).filter(models.Trip.id == trip_id).first()
        if trip:
            exit_measurement = db.query(models.ExitMeasurement).filter(
                models.ExitMeasurement.trip_id == trip_id
            ).first()
            
            if not exit_measurement:
                exit_measurement = models.ExitMeasurement(trip_id=trip_id)
                db.add(exit_measurement)
            
            if weighing_data["weight_type"] == "ТАРА":
                exit_measurement.weight_tare = weighing_data["weight"]
                
                # Рассчитать вес нетто
                if trip.entry_measurement:
                    net_weight = trip.entry_measurement.weight_brutto - weighing_data["weight"]
                    # Можно сохранить net_weight, если добавить поле в Trip
                
                trip.exit_time = datetime.now()
                trip.status = models.TripStatus.COMPLETED
            
            db.commit()
            db.refresh(trip)
        
        return trip


class VehicleCRUD:
    @staticmethod
    def get_or_create_by_plate(db: Session, plate_number: str) -> models.Vehicle:
        """Получить или создать автомобиль по госномеру"""
        # Нормализуем номер (убираем лишние пробелы)
        plate_number = plate_number.strip()
        
        # Ищем существующий автомобиль
        vehicle = db.query(models.Vehicle).filter(
            models.Vehicle.plate_number == plate_number
        ).first()
        
        if vehicle:
            logger.info(f"✅ Найден существующий автомобиль: {plate_number}")
            return vehicle
        
        # Если не найден - создаём новый
        logger.info(f"🆕 Создаём новый автомобиль: {plate_number}")
        vehicle = models.Vehicle(
            plate_number=plate_number,
            is_active=True,
            created_at=datetime.now()
        )
        db.add(vehicle)
        db.flush()  # Не commit, чтобы можно было использовать в транзакции
        return vehicle
    
    @staticmethod
    def get_by_plate(db: Session, plate_number: str) -> Optional[models.Vehicle]:
        """Получить автомобиль по госномеру"""
        return db.query(models.Vehicle).filter(
            models.Vehicle.plate_number == plate_number
        ).first()
    
    @staticmethod
    def get_or_create_carrier(db: Session, carrier_name: str) -> models.Carrier:
        """Получить или создать перевозчика"""
        if not carrier_name:
            return None
        
        carrier = db.query(models.Carrier).filter(
            models.Carrier.name == carrier_name
        ).first()
        
        if not carrier:
            carrier = models.Carrier(
                name=carrier_name,
                is_active=True
            )
            db.add(carrier)
            db.flush()
        
        return carrier