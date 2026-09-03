import { useCallback, useEffect, useRef, useState } from "react";
import { mockCamera, mockCurrent, mockHistory } from "./mock";
import type { CameraStatus, ControlCurrent, ControlEndpointStatus, ControlHistoryItem, ControlHistoryPage } from "./types";

const useMock = import.meta.env.VITE_USE_CONTROL_MOCK === "true";

console.log("CONTROL MOCK MODE", {
  raw: import.meta.env.VITE_USE_CONTROL_MOCK,
  useMock,
});

async function getJson<T>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

export function useControlCurrent() {
  const [data, setData] = useState<ControlCurrent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<ControlEndpointStatus>("checking");
  const latest = useRef<ControlCurrent | null>(null);
  useEffect(() => {
    let timer: number | undefined;
    let inFlight = false;
    let stopped = false;
    let controller: AbortController | null = null;
    const poll = async () => {
      console.log("CONTROL POLL START", {
        stopped,
        inFlight,
        useMock,
      });
      if (stopped || inFlight) return;
      inFlight = true;
      controller = new AbortController();
      try {
        if (!useMock) console.log("CONTROL FETCH", "/api/control/current");
        const next = useMock ? mockCurrent() : await getJson<ControlCurrent>("/api/control/current", controller.signal);
        console.log("CONTROL FETCH OK", next);
        latest.current = next;
        setData(next);
        setError(null);
        setStatus("online");
        console.log("CONTROL STATUS", "online");
      } catch (reason) {
        if (!controller.signal.aborted) {
          console.error("CONTROL FETCH ERROR", reason);
          setError(reason instanceof Error ? reason.message : "Нет связи с backend");
          setStatus("offline");
        }
      } finally {
        inFlight = false;
        if (!stopped) {
          const current = latest.current;
          const active = current?.active_session || (current?.scale.state_name && current.scale.state_name !== "Empty");
          timer = window.setTimeout(poll, document.hidden ? 10000 : active ? 750 : 4000);
        }
      }
    };
    void poll();
    const onVisibility = () => { if (!document.hidden && !inFlight) { window.clearTimeout(timer); void poll(); } };
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
  const pageSize = 10;
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<ControlHistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async (signal?: AbortSignal) => {
    const controller = signal ? null : new AbortController();
    try {
      const result = useMock ? { items: mockHistory.slice((page - 1) * pageSize, page * pageSize), total: mockHistory.length, page, page_size: pageSize, total_pages: Math.ceil(mockHistory.length / pageSize) } : await getJson<ControlHistoryPage>(`/api/control/history?page=${page}&page_size=${pageSize}`, signal || controller!.signal);
      setItems(result.items); setTotal(result.total); setTotalPages(result.total_pages); setError(null);
    } catch (reason) {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) setError("История временно недоступна");
    }
  }, [page]);
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    const timer = window.setInterval(() => { if (!document.hidden) void load(); }, 20000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [load, refreshKey]);
  return { items, error, refresh: load, page, pageSize, total, totalPages, setPage };
}
