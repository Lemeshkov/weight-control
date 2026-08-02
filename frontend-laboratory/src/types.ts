export type ExperimentStatus = "DRAFT" | "COMPLETED" | "ARCHIVED";
export type VolumeUnit = "LITER" | "M3";

export interface CoalGrade { id: number; code: string; name: string; description: string | null; is_active: boolean; }
export interface CoalFraction { id: number; name: string; min_size_mm: number | null; max_size_mm: number | null; is_active: boolean; }
export interface Supplier { id: number; code: string | null; name: string; is_active: boolean; }

export interface MeasurementInput {
  sequence_number: number;
  entered_volume_value: number;
  entered_volume_unit: VolumeUnit;
  material_mass_kg: number;
  is_included: boolean;
  exclusion_reason: string | null;
}
export interface Measurement extends MeasurementInput {
  id: number; experiment_id: number; container_volume_m3: number;
  calculated_density_kg_m3: number;
}
export interface ExperimentPayload {
  experiment_number: string; coal_grade_id: number; coal_fraction_id: number; supplier_id: number;
  batch_number: string | null; invoice_number: string | null; sampled_at: string | null;
  tested_at: string; moisture_percent: number | null; laboratory_user_name: string;
  comment: string | null; measurements: MeasurementInput[];
}
export interface Experiment extends Omit<ExperimentPayload, "measurements"> {
  id: number; status: ExperimentStatus; laboratory_user_id: number | null;
  created_at: string; updated_at: string; archived_at: string | null;
  measurements: Measurement[]; included_measurements_count: number; average_density_kg_m3: number | null;
}
export interface ExperimentListItem {
  id: number; experiment_number: string; tested_at: string; sampled_at?: string | null;
  coal_grade: string; coal_fraction: string; supplier: string; batch_number: string | null;
  invoice_number: string | null; measurements_count: number; average_density_kg_m3: number | null;
  moisture_percent: number | null; status: ExperimentStatus; laboratory_user_name: string;
}
export interface ExperimentListResponse { items: ExperimentListItem[]; total: number; limit: number; offset: number; }
export interface AuditEntry {
  id: number; action: string; changed_by_name: string | null; previous_values: Record<string, unknown> | null;
  new_values: Record<string, unknown> | null; created_at: string;
}
export interface ExperimentFilters {
  date_from?: string; date_to?: string; coal_grade_id?: number; supplier_id?: number;
  status?: ExperimentStatus | ""; search?: string; limit: number; offset: number;
}
