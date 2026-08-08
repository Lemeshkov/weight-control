import enum
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, Enum, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from database import Base


def utc_now():
    return datetime.now(timezone.utc)


class LabExperimentStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class LabVolumeUnit(str, enum.Enum):
    LITER = "LITER"
    M3 = "M3"


class CoalGrade(Base):
    __tablename__ = "coal_grades"
    id = Column(Integer, primary_key=True)
    code = Column(String(50), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class CoalFraction(Base):
    __tablename__ = "coal_fractions"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    min_size_mm = Column(Numeric(12, 3))
    max_size_mm = Column(Numeric(12, 3))
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class Supplier(Base):
    __tablename__ = "suppliers"
    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True)
    name = Column(String(255), nullable=False, unique=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class LabExperiment(Base):
    __tablename__ = "lab_experiments"
    id = Column(Integer, primary_key=True)
    experiment_number = Column(String(100), nullable=False, unique=True)
    coal_grade_id = Column(Integer, ForeignKey("coal_grades.id"), nullable=False, index=True)
    coal_fraction_id = Column(Integer, ForeignKey("coal_fractions.id"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    batch_number = Column(String(100), index=True)
    invoice_number = Column(String(100), index=True)
    sampled_at = Column(DateTime(timezone=True))
    tested_at = Column(DateTime(timezone=True), nullable=False, index=True)
    moisture_percent = Column(Numeric(7, 3))
    status = Column(Enum(LabExperimentStatus, name="lab_experiment_status"), nullable=False, default=LabExperimentStatus.DRAFT, index=True)
    laboratory_user_id = Column(Integer, ForeignKey("users.id"))
    laboratory_user_name = Column(String(255), nullable=False)
    comment = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    archived_at = Column(DateTime(timezone=True))
    coal_grade = relationship("CoalGrade")
    coal_fraction = relationship("CoalFraction")
    supplier = relationship("Supplier")
    measurements = relationship("LabMeasurement", back_populates="experiment", cascade="all, delete-orphan", order_by="LabMeasurement.sequence_number")
    audit_entries = relationship("LabAuditLog", back_populates="experiment", cascade="all, delete-orphan", order_by="LabAuditLog.created_at")


class LabMeasurement(Base):
    __tablename__ = "lab_measurements"
    __table_args__ = (UniqueConstraint("experiment_id", "sequence_number", name="uq_lab_measurement_sequence"),)
    id = Column(Integer, primary_key=True)
    experiment_id = Column(Integer, ForeignKey("lab_experiments.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence_number = Column(Integer, nullable=False)
    entered_volume_value = Column(Numeric(18, 6), nullable=False)
    entered_volume_unit = Column(Enum(LabVolumeUnit, name="lab_volume_unit"), nullable=False)
    container_volume_m3 = Column(Numeric(18, 9), nullable=False)
    material_mass_kg = Column(Numeric(18, 6), nullable=False)
    calculated_density_kg_m3 = Column(Numeric(18, 6), nullable=False)
    is_included = Column(Boolean, nullable=False, default=True)
    exclusion_reason = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    experiment = relationship("LabExperiment", back_populates="measurements")


class LabAuditLog(Base):
    __tablename__ = "lab_audit_log"
    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    experiment_id = Column(Integer, ForeignKey("lab_experiments.id", ondelete="CASCADE"), nullable=False, index=True)
    measurement_id = Column(Integer)
    action = Column(String(50), nullable=False)
    changed_by_user_id = Column(Integer, ForeignKey("users.id"))
    changed_by_name = Column(String(255))
    previous_values = Column(JSON().with_variant(JSONB, "postgresql"))
    new_values = Column(JSON().with_variant(JSONB, "postgresql"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    experiment = relationship("LabExperiment", back_populates="audit_entries")


class LabFuelQualityTest(Base):
    __tablename__ = "lab_fuel_quality_tests"
    id = Column(Integer, primary_key=True)
    sample_date = Column(Date, nullable=False, index=True)
    sample_name = Column(String(255), nullable=False, index=True)
    calorimeter = Column(String(100), nullable=False)
    sa_percent = Column(Numeric(9, 4), nullable=False)
    alpha = Column(Numeric(12, 8), nullable=False)
    wa_percent = Column(Numeric(9, 4), nullable=False)
    aa_percent = Column(Numeric(9, 4), nullable=False)
    wr_percent = Column(Numeric(9, 4), nullable=False)
    hydrogen_input_percent = Column(Numeric(9, 4), nullable=False)
    qb_a_1_kcal_kg = Column(Numeric(14, 2), nullable=False)
    qb_a_2_kcal_kg = Column(Numeric(14, 2), nullable=False)
    va_percent = Column(Numeric(9, 4), nullable=False)
    status = Column(Enum(LabExperimentStatus, name="lab_experiment_status", create_type=False), nullable=False, default=LabExperimentStatus.DRAFT, index=True)
    lab_technician_name = Column(String(255), nullable=False)
    wagon_numbers = Column(String(500))
    invoice_number = Column(String(100), index=True)
    fuel_consumption_note = Column(Text)
    calculation_snapshot = Column(JSON().with_variant(JSONB, "postgresql"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    archived_at = Column(DateTime(timezone=True))
    created_by = Column(Integer, ForeignKey("users.id"))
    updated_by = Column(Integer, ForeignKey("users.id"))
    audit_entries = relationship("LabFuelQualityAuditLog", back_populates="test", cascade="all, delete-orphan", order_by="LabFuelQualityAuditLog.created_at")


class LabFuelQualityAuditLog(Base):
    __tablename__ = "lab_fuel_quality_audit_log"
    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    test_id = Column(Integer, ForeignKey("lab_fuel_quality_tests.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String(50), nullable=False)
    changed_by_user_id = Column(Integer, ForeignKey("users.id"))
    changed_by_name = Column(String(255))
    previous_values = Column(JSON().with_variant(JSONB, "postgresql"))
    new_values = Column(JSON().with_variant(JSONB, "postgresql"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    test = relationship("LabFuelQualityTest", back_populates="audit_entries")
