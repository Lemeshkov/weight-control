import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useControlCurrent, useControlHistory } from "./hooks";

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe("control polling", () => {
  it("does not start a parallel request and aborts on unmount", async () => {
    vi.useFakeTimers();
    let capturedSignal: AbortSignal | undefined;
    const fetchMock = vi.fn((_url: string, options: RequestInit) => {
      capturedSignal = options.signal as AbortSignal;
      return new Promise<Response>(() => undefined);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { unmount } = renderHook(() => useControlCurrent());
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    unmount();
    expect(capturedSignal?.aborted).toBe(true);
  });


  it("moves from checking to online after a successful 200 response", async () => {
    const payload = {
      scale: { state_name: "Empty", massa: -50, stabil: true, connected: true },
      lidar: { connected: true, reader_running: true, buffer_profiles: 16, latest_sequence_number: 256, last_profile_at: null, last_error: null, recording: false, session_profiles: 0 },
      active_session: null,
      stable_confirmation: { current_count: 0, required_count: 3, last_reset_reason: null, last_sample_at: null },
      persistence_available: true, persistence_error: null, repository_mode: "sql",
    };
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify(payload), { status: 200 }))));
    const { result } = renderHook(() => useControlCurrent());
    expect(result.current.status).toBe("checking");
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)); });
    expect(result.current.status).toBe("online");
    expect(result.current.data?.lidar.reader_running).toBe(true);
  });

  it("moves from checking to offline when control/current fails", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("", { status: 503 }))));
    const { result } = renderHook(() => useControlCurrent());
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)); });
    expect(result.current.status).toBe("offline");
    expect(result.current.data).toBeNull();
  });
  it("refreshes history on its slow interval, not every 500ms", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ items: [] }), { status: 200 })));
    vi.stubGlobal("fetch", fetchMock);
    const { unmount } = renderHook(() => useControlHistory("idle"));
    await act(async () => { await Promise.resolve(); });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(500); });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(20000); });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    unmount();
  });
});
