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
