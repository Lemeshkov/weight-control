import type { CameraStatus, ControlCurrent, ControlEndpointStatus } from "./types";

type IndicatorState = "ok" | "warn" | "bad" | "unknown";

function Indicator({ label, state, text }: { label: string; state: IndicatorState; text: string }) {
  const icons = { ok: "●", warn: "▲", bad: "×", unknown: "○" };
  return <div className={`equipment equipment--${state}`} data-testid={`equipment-${label}`}>
    <span aria-hidden>{icons[state]}</span><div><b>{label}</b><small>{text}</small></div>
  </div>;
}

export function EquipmentStatusBar({ control, camera, controlStatus = control ? "online" : "checking" }: {
  control: ControlCurrent | null;
  camera: CameraStatus | null;
  controlStatus?: ControlEndpointStatus;
}) {
  const checking = controlStatus === "checking";
  const endpointOffline = controlStatus === "offline";
  const scaleOnline = control?.scale.connected === true;
  const lidarOnline = control?.lidar.connected === true && control.lidar.reader_running === true;
  const databaseOnline = control?.persistence_available === true && control.repository_mode === "sql";

  const device = (online: boolean): { state: IndicatorState; text: string } =>
    checking ? { state: "unknown", text: "Проверка…" } : endpointOffline
      ? { state: "bad", text: "Нет связи" }
      : online ? { state: "ok", text: "Онлайн" } : { state: "bad", text: "Нет связи" };
  const scale = device(scaleOnline);
  const lidar = device(lidarOnline);
  const repository: { state: IndicatorState; text: string } = checking
    ? { state: "unknown", text: "Проверка…" }
    : endpointOffline ? { state: "bad", text: "Нет связи" }
    : control?.repository_mode === "memory" ? { state: "warn", text: "Ограниченный / Memory fallback" }
    : databaseOnline ? { state: "ok", text: "Онлайн / SQL" }
    : { state: "bad", text: "Нет связи" };

  return <section className="equipment-bar" aria-label="Состояние оборудования">
    <Indicator label="Весы" {...scale} />
    <Indicator label="Лидар" {...lidar} />
    <Indicator label="Камера" state={!camera ? "unknown" : camera.connected ? "ok" : "bad"} text={!camera ? "Проверка…" : camera.connected ? "Онлайн" : "Нет связи"} />
    <Indicator label="База данных" {...repository} />
  </section>;
}
