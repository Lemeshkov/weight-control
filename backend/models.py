# app/models.py
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text, JSON, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from database import Base 


class TripStatus(str, enum.Enum):
    ENTRY = "entry"  # На въезде
    EXIT = "exit"    # На выезде
    COMPLETED = "completed"  # Завершен
    REJECTED = "rejected"    # Отклонен

class ResidueType(str, enum.Enum):
    CLEAN = "clean"
    RESIDUE = "residue"
    DIRT = "dirt"
    UNKNOWN = "unknown"

# Справочники
class Carrier(Base):
    __tablename__ = "carriers"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    inn = Column(String(12), unique=True)
    contact_person = Column(String(255))
    phone = Column(String(20))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    vehicles = relationship("Vehicle", back_populates="carrier")
    trips = relationship("Trip", back_populates="carrier")
    batch_densities = relationship("BatchDensity", back_populates="carrier")

class Vehicle(Base):
    __tablename__ = "vehicles"
    
    id = Column(Integer, primary_key=True, index=True)
    plate_number = Column(String(20), nullable=False, unique=True)
    carrier_id = Column(Integer, ForeignKey("carriers.id"))
    model = Column(String(100))
    max_volume = Column(Float)  # Максимальный объем кузова в м³
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    carrier = relationship("Carrier", back_populates="vehicles")
    trips = relationship("Trip", back_populates="vehicle")

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50))  # admin, operator, viewer
    carrier_id = Column(Integer, ForeignKey("carriers.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    carrier = relationship("Carrier")

class Device(Base):
    __tablename__ = "devices"
    
    id = Column(Integer, primary_key=True, index=True)
    device_type = Column(String(50))  # scale, lidar, camera, uniserver
    model = Column(String(100))
    serial_number = Column(String(100), unique=True)
    location = Column(String(100))  # entry, exit
    last_calibration = Column(DateTime)
    is_active = Column(Boolean, default=True)

# Транзакционные таблицы
class Trip(Base):
    __tablename__ = "trips"
    
    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"))
    carrier_id = Column(Integer, ForeignKey("carriers.id"))
    driver_name = Column(String(255))
    entry_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    exit_time = Column(DateTime)
    status = Column(Enum(TripStatus), default=TripStatus.ENTRY)
    density_calculated = Column(Float)  # Расчетная плотность для рейса
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    vehicle = relationship("Vehicle", back_populates="trips")
    carrier = relationship("Carrier", back_populates="trips")
    entry_measurement = relationship("EntryMeasurement", back_populates="trip", uselist=False)
    exit_measurement = relationship("ExitMeasurement", back_populates="trip", uselist=False)
    stock_events = relationship("StockEvent", back_populates="trip")
    uniserver_events = relationship("UniserverEvent", back_populates="trip")

class EntryMeasurement(Base):
    __tablename__ = "entry_measurements"
    
    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), unique=True)
    weight_brutto = Column(Float, nullable=False)  # Вес брутто в кг
    volume_scan = Column(Float)  # Объем из лидара в м³
    photo_path = Column(String(500))  # Путь к фото
    photo_archive = Column(String(500))  # Путь к архиву фото
    neural_verdict = Column(String(50))  # coal, rock, dirt
    neural_confidence = Column(Float)  # Уверенность нейросети 0-1
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    trip = relationship("Trip", back_populates="entry_measurement")
    neural_log = relationship("NeuralLog", back_populates="measurement", foreign_keys="NeuralLog.measurement_id")

class ExitMeasurement(Base):
    __tablename__ = "exit_measurements"
    
    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), unique=True)
    weight_tare = Column(Float, nullable=False)  # Вес тары в кг
    residue_volume = Column(Float)  # Объем остатков из лидара в м³
    residue_type = Column(Enum(ResidueType))
    photo_path = Column(String(500))
    photo_archive = Column(String(500))
    neural_verdict = Column(String(50))  # clean, residue, dirt
    neural_confidence = Column(Float)
    is_approved = Column(Boolean, default=False)  # Подтвержден ли выезд
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    trip = relationship("Trip", back_populates="exit_measurement")
    neural_log = relationship("NeuralLog", back_populates="measurement", foreign_keys="NeuralLog.measurement_id")

# Аналитические и служебные
class NeuralLog(Base):
    __tablename__ = "neural_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    measurement_id = Column(Integer)  # ID из entry_measurements или exit_measurements
    measurement_type = Column(String(20))  # entry или exit
    model_version = Column(String(50))
    raw_features = Column(JSON)  # Признаки для нейросети
    result = Column(JSON)  # Результат распознавания
    processing_time_ms = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    measurement = relationship("EntryMeasurement", back_populates="neural_log", foreign_keys=[measurement_id])

class SystemLog(Base):
    __tablename__ = "system_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=True)
    device_type = Column(String(50))
    event_type = Column(String(50))  # error, warning, info
    message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    trip = relationship("Trip")

class StockEvent(Base):
    __tablename__ = "stock_events"
    
    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(20))  # income, outcome
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=True)
    volume = Column(Float)  # Объем в м³
    weight = Column(Float)  # Вес в тоннах
    density = Column(Float)  # Плотность т/м³
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    trip = relationship("Trip", back_populates="stock_events")

class BatchDensity(Base):
    __tablename__ = "batch_density"
    
    id = Column(Integer, primary_key=True, index=True)
    batch_name = Column(String(100), nullable=False)
    carrier_id = Column(Integer, ForeignKey("carriers.id"))
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    total_weight = Column(Float)  # Суммарный вес в тоннах
    total_volume = Column(Float)  # Суммарный объем в м³
    avg_density = Column(Float)  # Средняя плотность т/м³
    density_stddev = Column(Float)  # Стандартное отклонение
    created_at = Column(DateTime, default=datetime.utcnow)
    
    carrier = relationship("Carrier", back_populates="batch_densities")

class UniserverEvent(Base):
    __tablename__ = "uniserver_events"
    
    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=True)
    uniserver_event_id = Column(String(100))  # DocID из UniServer
    plate_number = Column(String(20))
    weight = Column(Float)
    raw_message = Column(JSON)  # Полный JSON от UniServer
    created_at = Column(DateTime, default=datetime.utcnow)
    
    trip = relationship("Trip", back_populates="uniserver_events")