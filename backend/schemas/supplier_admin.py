from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SupplierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    short_name: str | None = Field(None, max_length=100)
    inn: str | None = Field(None, max_length=20)
    comment: str | None = None

    @field_validator("name")
    @classmethod
    def trim_name(cls, value):
        value = value.strip()
        if not value: raise ValueError("Наименование поставщика обязательно")
        return value


class SupplierUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    short_name: str | None = Field(None, max_length=100)
    inn: str | None = Field(None, max_length=20)
    comment: str | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def trim_optional_name(cls, value):
        if value is None: return value
        value = value.strip()
        if not value: raise ValueError("Наименование поставщика обязательно")
        return value


class SupplierRead(ORMModel):
    id: int; code: str | None; name: str; short_name: str | None; inn: str | None; comment: str | None
    is_active: bool; created_at: datetime; updated_at: datetime


def normalize_registration_number(value: str) -> str:
    return "".join(value.strip().upper().split())


class VehicleCreate(BaseModel):
    registration_number: str = Field(min_length=1, max_length=32)
    make_model: str | None = Field(None, max_length=255)
    supplier_id: int
    valid_from: date = Field(default_factory=date.today)
    comment: str | None = None

    @field_validator("registration_number")
    @classmethod
    def validate_plate(cls, value):
        if not normalize_registration_number(value): raise ValueError("Госномер обязателен")
        return value.strip()


class VehicleUpdate(BaseModel):
    registration_number: str | None = Field(None, min_length=1, max_length=32)
    make_model: str | None = Field(None, max_length=255)
    comment: str | None = None
    is_active: bool | None = None


class VehicleReassign(BaseModel):
    supplier_id: int
    valid_from: date = Field(default_factory=date.today)
    comment: str | None = None


class AssignmentRead(ORMModel):
    id: int; vehicle_id: int; supplier_id: int; valid_from: date; valid_to: date | None; comment: str | None; created_at: datetime


class VehicleRead(ORMModel):
    id: int; registration_number: str; registration_number_normalized: str; make_model: str | None
    comment: str | None; is_active: bool; created_at: datetime; updated_at: datetime
    current_supplier_id: int | None = None; current_supplier_name: str | None = None


class CoalGradeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None

    @field_validator("code", "name")
    @classmethod
    def trim_grade(cls, value):
        value=value.strip()
        if not value: raise ValueError("Марка угля обязательна")
        return value


class CoalGradeUpdate(BaseModel):
    code: str | None = Field(None, min_length=1, max_length=50)
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    is_active: bool | None = None

    @field_validator("code", "name")
    @classmethod
    def trim_optional_grade(cls, value):
        if value is None:return value
        value=value.strip()
        if not value:raise ValueError("Марка угля обязательна")
        return value


class CoalGradeRead(ORMModel):
    id: int; code: str; name: str; description: str | None; is_active: bool; created_at: datetime; updated_at: datetime


class FractionSpecInput(BaseModel):
    fraction_min_mm: Decimal = Field(ge=0)
    fraction_max_mm: Decimal = Field(ge=0)
    operator: Literal["<", "<=", "=", ">=", ">"]
    value: Decimal = Field(ge=0)
    unit: str = Field(default="%", min_length=1, max_length=16)
    comment: str | None = None

    @model_validator(mode="after")
    def validate_values(self):
        if self.fraction_max_mm < self.fraction_min_mm: raise ValueError("Максимальная фракция не может быть меньше минимальной")
        if self.unit == "%" and self.value > 100: raise ValueError("Процент должен быть от 0 до 100")
        return self


class FractionSpecRead(FractionSpecInput, ORMModel):
    id: int


class CoalSpecCreate(BaseModel):
    supplier_id: int; coal_grade_id: int
    calorific_value: Decimal | None = Field(None, gt=0)
    calorific_value_unit: str = Field(default="kcal/kg", min_length=1, max_length=32)
    moisture_pct: Decimal | None = Field(None, ge=0, le=100)
    ash_pct: Decimal | None = Field(None, ge=0, le=100)
    valid_from: date = Field(default_factory=date.today)
    valid_to: date | None = None
    comment: str | None = None
    fractions: list[FractionSpecInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.valid_to and self.valid_to < self.valid_from: raise ValueError("Дата окончания не может быть раньше даты начала")
        return self


class CoalSpecReplace(CoalSpecCreate):
    pass


class CoalSpecUpdate(BaseModel):
    supplier_id: int | None = None
    coal_grade_id: int | None = None
    calorific_value: Decimal | None = Field(None, gt=0)
    calorific_value_unit: str | None = Field(None, min_length=1, max_length=32)
    moisture_pct: Decimal | None = Field(None, ge=0, le=100)
    ash_pct: Decimal | None = Field(None, ge=0, le=100)
    valid_from: date | None = None
    valid_to: date | None = None
    comment: str | None = None
    is_active: bool | None = None
    fractions: list[FractionSpecInput] | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("Дата окончания не может быть раньше даты начала")
        return self


class CoalSpecRead(ORMModel):
    id: int; supplier_id: int; coal_grade_id: int
    calorific_value: Decimal | None; calorific_value_unit: str; moisture_pct: Decimal | None; ash_pct: Decimal | None
    valid_from: date; valid_to: date | None; comment: str | None; is_active: bool; created_at: datetime; updated_at: datetime
    supplier_name: str | None = None; coal_grade_name: str | None = None
    fractions: list[FractionSpecRead]


class Page(BaseModel):
    items: list; total: int; page: int; page_size: int; total_pages: int
