export type DirectoryItem = { id: number; code?: string | null; name: string };
export type AcceptanceForm = {
  shipment_date: string; act_number: string; transport_invoice_number: string;
  document_net_weight_t: string; supplier_id: string; coal_grade_id: string;
  uk_number: string; invoice_number: string; receiver_name: string; notes: string;
};
export type QueueItem = {
  trip_id: number; status: "WAITING" | "DRAFT" | "COMPLETED"; has_warning: boolean;
  vehicle: { license_plate: string | null; model: string | null };
  entry_time: string; actual_net_weight_t: string | null;
  lidar: null | { status: string; profiles_count: number; volume_status: string; estimated_volume_m3: number | null };
  acceptance: null | AcceptanceForm & { id: number; updated_at: string; supplier?: DirectoryItem; coal_grade?: DirectoryItem };
  calculated: { difference_t: string | null; shortage_t: string | null; excess_t: string | null; accepted_weight_t: string | null };
};
