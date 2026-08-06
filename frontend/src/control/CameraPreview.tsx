import type { CameraStatus } from "./types";

export function CameraPreview({ active, camera }: { active: boolean; camera: CameraStatus | null }) {
  if (!active) return <div className="camera-placeholder">Камера включается только для активного проезда</div>;
  if (!camera?.connected) return <div className="camera-placeholder camera-placeholder--offline">Камера недоступна. Данные весов и лидара продолжают обновляться.</div>;
  return <img className="camera-stream" src="/api/camera/stream" alt="Текущая камера весовой" />;
}
