from datetime import date
from decimal import Decimal
from pydantic import BaseModel

class SupplierSummaryFilters(BaseModel):
    date_from: date
    date_to: date
    supplier_id: int | None = None

class SupplierSummaryRow(BaseModel):
    supplier_id: int
    supplier_name: str
    trip_count: int
    total_weight_t: Decimal
    total_volume_m3: None = None
    bulk_density_t_m3: None = None

class SupplierSummaryTotals(BaseModel):
    trip_count: int
    total_weight_t: Decimal
    total_volume_m3: None = None
    bulk_density_t_m3: None = None

class SupplierSummaryResponse(BaseModel):
    filters: SupplierSummaryFilters
    rows: list[SupplierSummaryRow]
    totals: SupplierSummaryTotals
