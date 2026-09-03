import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ActivePassCard } from "./ActivePassCard";
import { EquipmentStatusBar } from "./EquipmentStatusBar";
import { RecentTripsTable } from "./RecentTripsTable";
import { SystemWarningBanner } from "./SystemWarningBanner";
import type { ControlCurrent, ControlHistoryItem } from "./types";

const current = (state = "Empty", error: string | null = null): ControlCurrent => ({
  scale: { state_name: state, massa: state === "Weighing" ? 4850 : 0, stabil: false, connected: true },
  lidar: { connected: true, reader_running: true, buffer_profiles: 16, latest_sequence_number: 256, last_profile_at: null, last_error: null, recording: state !== "Empty", session_profiles: 31 },
  active_session: state === "Empty" ? null : { id: 2, session_key: "pass", status: error ? "COMPLETED" : "RECORDING", workflow_state: state, trip_id: 6, started_at: "2026-01-01T00:00:00Z", load_scale_at: "2026-01-01T00:00:01Z", stable_weight_at: null, ended_at: error ? "2026-01-01T00:01:00Z" : null, profiles_count: 31, pre_trigger_profiles_count: 17, data_file_path: error ? "pass.json" : null, error_message: error, volume_status: "NOT_CALCULATED", estimated_volume_m3: null },
  stable_confirmation: { current_count: 2, required_count: 3, last_reset_reason: null, last_sample_at: null },
  persistence_available: true, persistence_error: null, repository_mode: "sql",
});

const historyItem = (id: number): ControlHistoryItem => ({
  trip_id: id, entry_time: "2026-01-01T00:00:00Z", exit_time: null, status: "completed",
  vehicle: { brand: "Урал", license_plate: `А00${id}ВС` },
  weight: { value_kg: 4850, tare_kg: null, net_kg: null, stable: true, completed_at: null },
  lidar: { session_id: id, status: "COMPLETED", workflow_state: "COMPLETED", started_at: "2026-01-01T00:00:00Z", load_scale_at: "2026-01-01T00:00:01Z", stable_weight_at: null, ended_at: "2026-01-01T00:01:00Z", stable_weight_kg: 4850, maximum_observed_weight_kg: 4900, profiles_count: 37, pre_trigger_profiles_count: 17, valid_profiles_count: 35, points_total: 1000, points_valid: 900, data_file_path: "pass.json", error_message: null, volume_status: "NOT_CALCULATED", estimated_volume_m3: null }, photo_path: null,
});

describe("operator control components", () => {
  it("maps Empty and LoadScale to operator labels", () => {
    const { rerender } = render(<ActivePassCard control={current("Empty")} camera={{ connected: false, frame_timestamp: null, errors: 1 }} />);
    expect(screen.getByText("Весы свободны")).toBeTruthy();
    rerender(<ActivePassCard control={current("LoadScale")} camera={null} />);
    expect(screen.getByText("Автомобиль заезжает")).toBeTruthy();
  });

  it("shows mass, stable progress and offline camera without crashing", () => {
    render(<ActivePassCard control={current("Weighing")} camera={{ connected: false, frame_timestamp: null, errors: 1 }} />);
    expect(screen.getByText(/4.850 кг/)).toBeTruthy();
    expect(screen.getByText("Стабильный вес: 2 из 3")).toBeTruthy();
    expect(screen.getByText(/Камера недоступна/)).toBeTruthy();
  });

  it("treats stable_weight_missing as warning and never displays zero volume", () => {
    render(<ActivePassCard control={current("ReadyWeighing", "stable_weight_missing")} camera={null} />);
    expect(screen.getByText(/без подтверждённого стабильного веса/)).toBeTruthy();
    expect(screen.getByText("Не рассчитан")).toBeTruthy();
    expect(screen.queryByText(/0 м³/)).toBeNull();
  });

  it("shows unavailable lidar and SQL mode without fallback warning", () => {
    const value = current(); value.lidar.connected = false;
    render(<EquipmentStatusBar control={value} camera={{ connected: false, frame_timestamp: null, errors: 1 }} />);
    expect(screen.getAllByText("Нет связи").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Онлайн / SQL")).toBeTruthy();
    expect(screen.queryByText(/Временный режим/)).toBeNull();
  });

  it("shows memory fallback warning but not in SQL mode", () => {
    const value = current(); value.repository_mode = "memory"; value.persistence_available = false;
    const { rerender } = render(<SystemWarningBanner control={value} backendError={null} />);
    expect(screen.getByText("Временный режим хранения.")).toBeTruthy();
    value.repository_mode = "sql"; value.persistence_available = true;
    rerender(<SystemWarningBanner control={value} backendError={null} />);
    expect(screen.queryByText("Временный режим хранения.")).toBeNull();
  });

  it("uses the real control/current DTO for scale, lidar and SQL statuses", () => {
    const realResponse: ControlCurrent = {
      scale: { state_name: "Empty", massa: -50, stabil: true, connected: true },
      lidar: { connected: true, reader_running: true, buffer_profiles: 16, latest_sequence_number: 256, last_profile_at: null, last_error: null, recording: false, session_profiles: 0 },
      active_session: null,
      stable_confirmation: { current_count: 0, required_count: 3, last_reset_reason: null, last_sample_at: null },
      persistence_available: true,
      persistence_error: null,
      repository_mode: "sql",
    };
    render(<EquipmentStatusBar control={realResponse} controlStatus="online" camera={null} />);
    expect(screen.getByTestId("equipment-Весы").className).toContain("equipment--ok");
    expect(screen.getByTestId("equipment-Лидар").className).toContain("equipment--ok");
    expect(screen.getByTestId("equipment-База данных").className).toContain("equipment--ok");
    expect(screen.getByTestId("equipment-Камера").className).toContain("equipment--unknown");
    expect(screen.getByText("Онлайн / SQL")).toBeTruthy();
  });

  it("shows memory as limited and a failed endpoint as offline, not checking", () => {
    const memory = current(); memory.repository_mode = "memory"; memory.persistence_available = false;
    const { rerender } = render(<EquipmentStatusBar control={memory} controlStatus="online" camera={null} />);
    expect(screen.getByTestId("equipment-База данных").className).toContain("equipment--warn");
    expect(screen.getByText("Ограниченный / Memory fallback")).toBeTruthy();
    rerender(<EquipmentStatusBar control={null} controlStatus="offline" camera={null} />);
    expect(screen.getByTestId("equipment-Весы").className).toContain("equipment--bad");
    expect(screen.getByTestId("equipment-Лидар").className).toContain("equipment--bad");
    expect(screen.getByTestId("equipment-База данных").className).toContain("equipment--bad");
    expect(screen.getAllByText("Нет связи")).toHaveLength(3);
    expect(screen.queryByText("Проверка…")).toBeTruthy(); // camera is checked independently
  });
  it("shows saved JSON details, no historical photo, and creates no camera streams", () => {
    render(<RecentTripsTable items={[historyItem(1), historyItem(2)]} error={null} refresh={() => undefined} page={1} totalPages={1} total={2} onPageChange={() => undefined} />);
    const buttons = screen.getAllByText("Подробнее");
    fireEvent.click(buttons[0]);
    expect(screen.getByText("JSON: pass.json")).toBeTruthy();
    expect(screen.getByText("Фото проезда не сохранялось")).toBeTruthy();
    fireEvent.click(buttons[1]);
    expect(document.querySelectorAll('img[src="/api/camera/stream"]')).toHaveLength(0);
  });
  it("shows compact pagination and changes pages", () => {
    let selected = 0;
    render(<RecentTripsTable items={[historyItem(1)]} error={null} refresh={() => undefined} page={2} totalPages={4} total={37} onPageChange={page => { selected = page; }} />);
    expect(screen.getByText("Страница 2 из 4 · всего 37")).toBeTruthy();
    fireEvent.click(screen.getByText("Вперёд"));
    expect(selected).toBe(3);
    fireEvent.click(screen.getByText("Назад"));
    expect(selected).toBe(1);
  });
});
