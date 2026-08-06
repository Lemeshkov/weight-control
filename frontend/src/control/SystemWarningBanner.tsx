import type { ControlCurrent } from "./types";

export function SystemWarningBanner({ control, backendError }: { control: ControlCurrent | null; backendError: string | null }) {
  return <>
    {backendError && <div className="notice notice--error">Backend временно недоступен. История и навигация продолжат работать после восстановления связи.</div>}
    {control?.repository_mode === "memory" && <div className="notice notice--warn"><b>Временный режим хранения.</b> Метаданные сессий могут быть потеряны после перезапуска backend. JSON-файлы продолжают сохраняться.</div>}
  </>;
}
