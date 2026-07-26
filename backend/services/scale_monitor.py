"""
Мониторинг весов и автоматическое создание рейсов
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from database import SessionLocal
import models
from services.uniserver_client import uniserver_client
from crud import VehicleCRUD, TripCRUD

logger = logging.getLogger(__name__)


class ScaleMonitor:
    """Мониторинг весов и автоматическое создание рейсов"""
    
    def __init__(self):
        self.running = False
        self.task = None
        self.last_state = {}
        self.last_trip_id = {}
    
    async def start(self):
        """Запуск мониторинга"""
        if self.running:
            return
        
        self.running = True
        logger.info("🔄 Запущен мониторинг весов")
        self.task = asyncio.create_task(self._monitor_loop())
    
    async def _monitor_loop(self):
        """Цикл мониторинга в фоне"""
        while self.running:
            try:
                await self.check_scale()
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                logger.info("⏹ Мониторинг остановлен")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка мониторинга: {e}")
                await asyncio.sleep(5)
    
    async def check_scale(self):
        """Проверка весов"""
        try:
            data = await uniserver_client.get_current_weighting()
            if not data:
                return
            
            plate_number = data.get('plate_number', '')
            weight = data.get('weight', 0)
            is_stable = data.get('is_stable', False)
            weight_type = data.get('weight_type', '')
            
            if not plate_number or plate_number.strip() == "":
                return
            
            if weight <= 0:
                return
            
            key = f"{plate_number}_{weight_type}"
            current_state = {"weight": weight, "is_stable": is_stable}
            
            if key in self.last_state:
                last = self.last_state[key]
                if last["weight"] == weight and last["is_stable"] == is_stable:
                    return
            
            self.last_state[key] = current_state
            
            if is_stable and weight_type in ["БРУТТО", "BRUTTO", "GROSS"]:
                await self._handle_entry(plate_number, weight, data)
            elif is_stable and weight_type in ["ТАРА", "TARE", "NET"]:
                await self._handle_exit(plate_number, weight, data)
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки весов: {e}")
    
    async def _handle_entry(self, plate_number: str, weight: float, data: dict):
        """Обработка въезда"""
        db = SessionLocal()
        try:
            vehicle = VehicleCRUD.get_or_create_by_plate(db, plate_number)
            
            active_trip = TripCRUD.get_trip_by_vehicle_and_status(
                db, vehicle.id, models.TripStatus.ENTRY
            )
            
            if active_trip:
                logger.info(f"ℹ️ Уже есть активный рейс {active_trip.id} для {plate_number}")
                return
            
            trip = models.Trip(
                vehicle_id=vehicle.id,
                entry_time=datetime.now(),
                status=models.TripStatus.ENTRY
            )
            db.add(trip)
            db.flush()
            
            entry = models.EntryMeasurement(
                trip_id=trip.id,
                weight_brutto=weight
            )
            db.add(entry)
            
            db.commit()
            logger.info(f"🚛 ✅ СОЗДАН РЕЙС {trip.id} для {plate_number}, вес {weight} кг")
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания рейса: {e}")
            db.rollback()
        finally:
            db.close()
    
    async def _handle_exit(self, plate_number: str, weight: float, data: dict):
        """Обработка выезда"""
        db = SessionLocal()
        try:
            vehicle = VehicleCRUD.get_by_plate(db, plate_number)
            if not vehicle:
                logger.warning(f"⚠️ Автомобиль {plate_number} не найден")
                return
            
            active_trip = TripCRUD.get_trip_by_vehicle_and_status(
                db, vehicle.id, models.TripStatus.ENTRY
            )
            
            if not active_trip:
                logger.warning(f"⚠️ Нет активного рейса для {plate_number}")
                return
            
            exit_measurement = models.ExitMeasurement(
                trip_id=active_trip.id,
                weight_tare=weight
            )
            db.add(exit_measurement)
            
            active_trip.exit_time = datetime.now()
            active_trip.status = models.TripStatus.COMPLETED
            
            db.commit()
            logger.info(f"🚛 ✅ ЗАВЕРШЕН РЕЙС {active_trip.id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка завершения рейса: {e}")
            db.rollback()
        finally:
            db.close()
    
    async def stop(self):
        """Остановка мониторинга с ожиданием завершения фоновой задачи."""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
        logger.info("⏹ Мониторинг весов остановлен")


scale_monitor = ScaleMonitor()