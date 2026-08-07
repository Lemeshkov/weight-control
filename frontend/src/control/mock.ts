import type { CameraStatus, ControlCurrent, ControlHistoryItem } from "./types";

const started = Date.now();

export function mockCurrent(): ControlCurrent {
  const phase = Math.floor((Date.now() - started) / 4000) % 6;
  const states = ["Empty", "LoadScale", "Weighing", "Weighing", "ReadyWeighing", "WeighingComplete"];
  const state = states[phase];
  const active = phase > 0 && phase < 5;
  const profiles = active ? 12 + phase * 9 : 0;
  return {
    scale: { state_name: state, plate_number: active ? "А123ВС142" : "", massa: phase < 2 ? phase * 900 : 4850, stabil: phase >= 3, connected: true },
    lidar: { connected: phase !== 2, reader_running: phase !== 2, buffer_profiles: 16, latest_sequence_number: 256, last_profile_at: new Date().toISOString(), last_error: null, recording: active, session_profiles: profiles },
    active_session: active ? {
      id: 2, session_key: "demo-pass", status: "RECORDING", workflow_state: state,
      trip_id: 6, started_at: new Date(started).toISOString(), load_scale_at: new Date(started + 4000).toISOString(),
      stable_weight_at: phase >= 4 ? new Date().toISOString() : null, ended_at: null,
      profiles_count: profiles, pre_trigger_profiles_count: 12, data_file_path: null,
      error_message: null, volume_status: "NOT_CALCULATED", estimated_volume_m3: null,
    } : null,
    stable_confirmation: { current_count: phase === 2 ? 1 : phase === 3 ? 2 : phase >= 4 ? 3 : 0, required_count: 3, last_reset_reason: null, last_sample_at: new Date().toISOString() },
    persistence_available: true, persistence_error: null, repository_mode: "sql",
  };
}

export const mockCamera: CameraStatus = { connected: false, frame_timestamp: null, errors: 1 };

export const mockHistory: ControlHistoryItem[] = [{
  trip_id: 5, entry_time: new Date(started - 600000).toISOString(), exit_time: new Date(started - 540000).toISOString(), status: "completed",
  vehicle: { brand: "Урал 5557", license_plate: "А123ВС142" },
  weight: { value_kg: 4850, tare_kg: null, net_kg: null, stable: true, completed_at: new Date(started - 550000).toISOString() },
  lidar: { session_id: 1, status: "COMPLETED", workflow_state: "COMPLETED", started_at: new Date(started - 600000).toISOString(), load_scale_at: new Date(started - 595000).toISOString(), stable_weight_at: new Date(started - 570000).toISOString(), ended_at: new Date(started - 550000).toISOString(), stable_weight_kg: 4850, maximum_observed_weight_kg: 4890, profiles_count: 37, pre_trigger_profiles_count: 17, valid_profiles_count: 37, points_total: 21090, points_valid: 18840, data_file_path: "data/lidar_passes/demo.json", error_message: null, volume_status: "NOT_CALCULATED", estimated_volume_m3: null },
  photo_path: null,
}];
