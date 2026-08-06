export interface LidarSession {
  id: number | null;
  session_key: string;
  status: "RECORDING" | "COMPLETED" | "FAILED";
  workflow_state: string;
  trip_id: number | null;
  started_at: string;
  load_scale_at: string;
  stable_weight_at: string | null;
  ended_at: string | null;
  profiles_count: number;
  pre_trigger_profiles_count: number;
  data_file_path: string | null;
  error_message: string | null;
  volume_status: string;
  estimated_volume_m3: number | null;
}

export interface ControlCurrent {
  scale: { state_name: string | null; plate_number?: string | null; massa: number | null; stabil: boolean | null; connected: boolean };
  lidar: { connected?: boolean; is_connected?: boolean; recording: boolean; session_profiles: number; last_error?: string | null };
  active_session: LidarSession | null;
  stable_confirmation: { current_count: number; required_count: number; last_reset_reason: string | null; last_sample_at: string | null };
  persistence_available: boolean;
  persistence_error: string | null;
  repository_mode: "sql" | "memory" | string;
}

export interface CameraStatus {
  connected: boolean;
  frame_timestamp: string | null;
  errors: number;
}

export interface HistoryLidar {
  session_id: number;
  session_key?: string | null;
  status: string;
  workflow_state: string;
  started_at: string;
  load_scale_at: string;
  stable_weight_at: string | null;
  ended_at: string | null;
  stable_weight_kg: number | null;
  maximum_observed_weight_kg: number | null;
  profiles_count: number;
  pre_trigger_profiles_count: number;
  valid_profiles_count: number;
  points_total: number;
  points_valid: number;
  data_file_path: string | null;
  error_message: string | null;
  volume_status: string;
  estimated_volume_m3: number | null;
}

export interface ControlHistoryItem {
  trip_id: number;
  entry_time: string;
  exit_time: string | null;
  status: string;
  vehicle: { brand: string | null; license_plate: string };
  weight: { value_kg: number | null; tare_kg: number | null; net_kg: number | null; stable: boolean; completed_at: string | null };
  lidar: HistoryLidar | null;
  photo_path: string | null;
}
