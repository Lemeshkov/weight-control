import type { CameraStatus, ControlCurrent } from "./types";

function Indicator({ label, state, text }: { label: string; state: "ok" | "warn" | "bad" | "unknown"; text: string }) {
  const icons = { ok: "●", warn: "▲", bad: "×", unknown: "○" };
  return <div className={`equipment equipment--${state}`}><span aria-hidden>{icons[state]}</span><div><b>{label}</b><small>{text}</small></div></div>;
}

export function EquipmentStatusBar({ control, camera }: { control: ControlCurrent | null; camera: CameraStatus | null }) {
  const lidarConnected = Boolean(control?.lidar.connected ?? control?.lidar.is_connected);
  const repository = !control ? ["unknown", "Проверка…"] : control.repository_mode === "sql" && control.persistence_available ? ["ok", "SQL"] : control.repository_mode === "memory" ? ["warn", "Memory fallback"] : ["bad", "Нет связи"];
  return <section className="equipment-bar" aria-label="Состояние оборудования">
    <Indicator label="Весы" state={!control ? "unknown" : control.scale.connected ? "ok" : "bad"} text={!control ? "Проверка…" : control.scale.connected ? "Онлайн" : "Нет связи"} />
    <Indicator label="Лидар" state={!control ? "unknown" : lidarConnected ? "ok" : "bad"} text={!control ? "Проверка…" : lidarConnected ? "Онлайн" : "Нет связи"} />
    <Indicator label="Камера" state={!camera ? "unknown" : camera.connected ? "ok" : "bad"} text={!camera ? "Проверка…" : camera.connected ? "Онлайн" : "Нет связи"} />
    <Indicator label="База данных" state={repository[0] as "ok" | "warn" | "bad" | "unknown"} text={repository[1]} />
  </section>;
}
