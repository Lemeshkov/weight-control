from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lab_models import LabExperimentStatus, LabVolumeUnit


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CoalGradeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class CoalGradeRead(ORMModel):
    id: int
    code: str
    name: str
    description: str | None
    is_active: bool


class CoalFractionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    min_size_mm: Decimal | None = Field(default=None, ge=0)
    max_size_mm: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_range(self):
        if self.min_size_mm is not None and self.max_size_mm is not None and self.min_size_mm > self.max_size_mm:
            raise ValueError("min_size_mm must not exceed max_size_mm")
        return self


class CoalFractionRead(ORMModel):
    id: int
    name: str
    min_size_mm: Decimal | None
    max_size_mm: Decimal | None
    is_active: bool


class SupplierCreate(BaseModel):
    code: str | None = Field(default=None, max_length=50)
    name: str = Field(min_length=1, max_length=255)


class SupplierRead(ORMModel):
    id: int
    code: str | None
    name: str
    is_active: bool


class MeasurementInput(BaseModel):
    sequence_number: int = Field(gt=0)
    entered_volume_value: Decimal = Field(gt=0)
    entered_volume_unit: LabVolumeUnit
    material_mass_kg: Decimal = Field(gt=0)
    is_included: bool = True
    exclusion_reason: str | None = None

    @model_validator(mode="after")
    def validate_exclusion(self):
        if not self.is_included and not (self.exclusion_reason or "").strip():
            raise ValueError("exclusion_reason is required for excluded measurement")
        return self


class MeasurementUpdate(BaseModel):
    sequence_number: int | None = Field(default=None, gt=0)
    entered_volume_value: Decimal | None = Field(default=None, gt=0)
    entered_volume_unit: LabVolumeUnit | None = None
    material_mass_kg: Decimal | None = Field(default=None, gt=0)
    is_included: bool | None = None
    exclusion_reason: str | None = None


class MeasurementRead(ORMModel):
    id: int
    experiment_id: int
    sequence_number: int
    entered_volume_value: Decimal
    entered_volume_unit: LabVolumeUnit
    container_volume_m3: Decimal
    material_mass_kg: Decimal
    calculated_density_kg_m3: Decimal
    is_included: bool
    exclusion_reason: str | None


class ExperimentCreate(BaseModel):
    experiment_number: str = Field(min_length=1, max_length=100)
    coal_grade_id: int
    coal_fraction_id: int
    supplier_id: int
    batch_number: str | None = Field(default=None, max_length=100)
    invoice_number: str | None = Field(default=None, max_length=100)
    sampled_at: datetime | None = None
    tested_at: datetime
    moisture_percent: Decimal | None = Field(default=None, ge=0, le=100)
    laboratory_user_id: int | None = None
    laboratory_user_name: str = Field(min_length=1, max_length=255)
    comment: str | None = None
    measurements: list[MeasurementInput] = Field(default_factory=list)


class ExperimentUpdate(BaseModel):
    coal_grade_id: int | None = None
    coal_fraction_id: int | None = None
    supplier_id: int | None = None
    batch_number: str | None = None
    invoice_number: str | None = None
    sampled_at: datetime | None = None
    tested_at: datetime | None = None
    moisture_percent: Decimal | None = Field(default=None, ge=0, le=100)
    laboratory_user_id: int | None = None
    laboratory_user_name: str | None = Field(default=None, min_length=1)
    comment: str | None = None


class ExperimentRead(ORMModel):
    id: int
    experiment_number: str
    coal_grade_id: int
    coal_fraction_id: int
    supplier_id: int
    batch_number: str | None
    invoice_number: str | None
    sampled_at: datetime | None
    tested_at: datetime
    moisture_percent: Decimal | None
    status: LabExperimentStatus
    laboratory_user_id: int | None
    laboratory_user_name: str
    comment: str | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    measurements: list[MeasurementRead]
    included_measurements_count: int = 0
    average_density_kg_m3: Decimal | None = None


class ExperimentListItem(BaseModel):
    id: int
    experiment_number: str
    tested_at: datetime
    sampled_at: datetime | None
    coal_grade: str
    coal_fraction: str
    supplier: str
    batch_number: str | None
    invoice_number: str | None
    measurements_count: int
    average_density_kg_m3: Decimal | None
    moisture_percent: Decimal | None
    status: LabExperimentStatus
    laboratory_user_name: str


class ExperimentListResponse(BaseModel):
    items: list[ExperimentListItem]
    total: int
    limit: int
    offset: int


class AuditRead(ORMModel):
    id: int
    experiment_id: int
    measurement_id: int | None
    action: str
    changed_by_user_id: int | None
    changed_by_name: str | None
    previous_values: dict[str, Any] | None
    new_values: dict[str, Any] | None
    created_at: datetime
