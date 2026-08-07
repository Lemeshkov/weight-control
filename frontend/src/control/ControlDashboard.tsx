import { ActivePassCard } from "./ActivePassCard";
import { EquipmentStatusBar } from "./EquipmentStatusBar";
import { RecentTripsTable } from "./RecentTripsTable";
import { SystemWarningBanner } from "./SystemWarningBanner";
import { useCameraStatus, useControlCurrent, useControlHistory } from "./hooks";

export function ControlDashboard() {
  const { data: control, error: controlError, status: controlStatus } = useControlCurrent();
  const camera = useCameraStatus();
  const refreshKey = `${control?.active_session?.session_key || "none"}:${control?.active_session?.status || "idle"}`;
  const history = useControlHistory(refreshKey);
  return <main className="dashboard">
    <EquipmentStatusBar control={control} camera={camera} controlStatus={controlStatus} />
    <SystemWarningBanner control={control} backendError={controlError} />
    <ActivePassCard control={control} camera={camera} />
    <RecentTripsTable items={history.items} error={history.error} refresh={() => void history.refresh()} />
  </main>;
}
