import { useCallback, useEffect, useRef, useState } from "react";
import { mockCamera, mockCurrent, mockHistory } from "./mock";
import type { CameraStatus, ControlCurrent, ControlEndpointStatus, ControlHistoryItem } from "./types";

const useMock = import.meta.env.VITE_USE_CONTROL_MOCK === "true";

async function getJson<T>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

export function useControlCurrent() {
  const [data, setData] = useState<ControlCurrent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<ControlEndpointStatus>("checking");
  const inFlight = useRef(false);
  const latest = useRef<ControlCurrent | null>(null);
  useEffect(() => {
    let timer: number | undefined;
    let stopped = false;
    let controller: AbortController | null = null;
    const poll = async () => {
      if (stopped || inFlight.current) return;
      inFlight.current = true;
      controller = new AbortController();
      try {
        const next = useMock ? mockCurrent() : await getJson<ControlCurrent>("/api/control/current", controller.signal);
        latest.current = next;
        setData(next);
        setError(null);
        setStatus("online");
      } catch (reason) {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "Нет связи с backend");
          setStatus("offline");
        }
      } finally {
        inFlight.current = false;
        if (!stopped) {
          const current = latest.current;
          const active = current?.active_session || (current?.scale.state_name && current.scale.state_name !== "Empty");
          timer = window.setTimeout(poll, document.hidden ? 10000 : active ? 750 : 4000);
        }
      }
    };
    void poll();
    const onVisibility = () => { if (!document.hidden && !inFlight.current) { window.clearTimeout(timer); void poll(); } };
    document.addEventListener("visibilitychange", onVisibility);
    return () => { stopped = true; window.clearTimeout(timer); controller?.abort(); document.removeEventListener("visibilitychange", onVisibility); };
  }, []);
  return { data, error, status };
}

export function useCameraStatus() {
  const [data, setData] = useState<CameraStatus | null>(null);
  useEffect(() => {
    let timer: number | undefined;
    let stopped = false;
    let controller: AbortController | null = null;
    const poll = async () => {
      controller = new AbortController();
      try { setData(useMock ? mockCamera : await getJson<CameraStatus>("/api/camera/status", controller.signal)); }
      catch { setData({ connected: false, frame_timestamp: null, errors: 1 }); }
      finally { if (!stopped) timer = window.setTimeout(poll, document.hidden ? 30000 : 10000); }
    };
    void poll();
    return () => { stopped = true; window.clearTimeout(timer); controller?.abort(); };
  }, []);
  return data;
}

export function useControlHistory(refreshKey: string) {
  const [items, setItems] = useState<ControlHistoryItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async (signal?: AbortSignal) => {
    const controller = signal ? null : new AbortController();
    try {
      const result = useMock ? { items: mockHistory } : await getJson<{ items: ControlHistoryItem[] }>("/api/control/history", signal || controller!.signal);
      setItems(result.items); setError(null);
    } catch (reason) {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) setError("История временно недоступна");
    }
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    const timer = window.setInterval(() => { if (!document.hidden) void load(); }, 20000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [load, refreshKey]);
  return { items, error, refresh: load };
}
