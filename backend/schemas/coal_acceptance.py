from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field

class AcceptanceWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shipment_date: date | None = None
    act_number: str | None = Field(None, max_length=100)
    transport_invoice_number: str | None = Field(None, max_length=100)
    document_net_weight_t: Decimal | None = Field(None, gt=0)
    supplier_id: int | None = None
    coal_grade_id: int | None = None
    uk_number: str | None = Field(None, max_length=100)
    invoice_number: str | None = Field(None, max_length=100)
    receiver_name: str | None = Field(None, max_length=255)
    notes: str | None = None
    operator_name: str | None = Field(None, max_length=255)

class AcceptanceUpdate(AcceptanceWrite):
    expected_updated_at: datetime

class CompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_updated_at: datetime
    operator_name: str | None = Field(None, max_length=255)

