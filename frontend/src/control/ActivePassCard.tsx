import { CameraPreview } from "./CameraPreview";
import { kg, lidarLabels, scaleLabels, volumeLabels } from "./format";
import type { CameraStatus, ControlCurrent } from "./types";

export function ActivePassCard({ control, camera }: { control: ControlCurrent | null; camera: CameraStatus | null }) {
  if (!control) return <section className="active-card"><h2>Текущий проезд</h2><div className="empty-state">Ожидание данных backend…</div></section>;
  const session = control.active_session;
  const state = control.scale.state_name || "Unknown";
  const stable = control.stable_confirmation;
  return <section className="active-card">
    <div className="active-card__header"><div><span className="eyebrow">Текущий проезд</span><h2>{scaleLabels[state] || state}</h2></div><span className={`pass-state pass-state--${state === "Empty" ? "idle" : "active"}`}>{state === "Empty" ? "Свободно" : "Проезд активен"}</span></div>
    <div className="active-layout">
      <div>
        <div className="mass">{kg(control.scale.massa)}</div>
        <div className="stable-progress"><span>Стабильный вес: {stable.current_count} из {stable.required_count}</span><progress value={stable.current_count} max={stable.required_count} /></div>
        <dl className="facts">
          <div><dt>Автомобиль</dt><dd>{control.scale.plate_number || "Не определён"}</dd></div>
          <div><dt>Trip</dt><dd>{session?.trip_id ? `№${session.trip_id}` : "Ещё не привязан"}</dd></div>
          <div><dt>Лидар</dt><dd>{session ? lidarLabels[session.status] || session.status : "Нет активной записи"}</dd></div>
          <div><dt>Профилей</dt><dd>{session?.profiles_count ?? control.lidar.session_profiles ?? 0}</dd></div>
          <div><dt>Предтриггерных</dt><dd>{session?.pre_trigger_profiles_count ?? "—"}</dd></div>
          <div><dt>Объём</dt><dd>{volumeLabels[session?.volume_status || "NOT_CALCULATED"] || session?.volume_status}</dd></div>
        </dl>
        {session?.error_message === "stable_weight_missing" && <div className="notice notice--warn">Взвешивание завершено без подтверждённого стабильного веса</div>}
      </div>
      <CameraPreview active={state !== "Empty"} camera={camera} />
    </div>
  </section>;
}
