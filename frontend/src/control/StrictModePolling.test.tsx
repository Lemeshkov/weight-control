import { StrictMode } from "react";
import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ControlDashboard } from "./ControlDashboard";

const current = {
  scale: { state_name: "Empty", massa: -50, stabil: true, connected: true },
  lidar: { connected: true, reader_running: true, buffer_profiles: 16, latest_sequence_number: 256, last_profile_at: null, last_error: null, recording: false, session_profiles: 0 },
  active_session: null,
  stable_confirmation: { current_count: 0, required_count: 3, last_reset_reason: null, last_sample_at: null },
  persistence_available: true,
  persistence_error: null,
  repository_mode: "sql",
};

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("StrictMode polling lifecycle", () => {
  it("restarts after cleanup abort and leaves one working polling loop", async () => {
    vi.useFakeTimers();
    let controlCalls = 0;
    let abortedControlCalls = 0;
    let activeControlCalls = 0;
    let maxActiveControlCalls = 0;
    const fetchMock = vi.fn((input: RequestInfo | URL, options?: RequestInit) => {
      const url = String(input);
      if (url === "/api/control/current") {
        controlCalls += 1;
        activeControlCalls += 1;
        maxActiveControlCalls = Math.max(maxActiveControlCalls, activeControlCalls);
        if (controlCalls === 1) {
          return new Promise<Response>((_resolve, reject) => {
            options?.signal?.addEventListener("abort", () => {
              abortedControlCalls += 1;
              activeControlCalls -= 1;
              reject(new DOMException("The operation was aborted", "AbortError"));
            }, { once: true });
          });
        }
        activeControlCalls -= 1;
        return Promise.resolve(new Response(JSON.stringify(current), { status: 200 }));
      }
      if (url === "/api/camera/status") {
        return Promise.resolve(new Response(JSON.stringify({ connected: true, frame_timestamp: null, errors: 0 }), { status: 200 }));
      }
      if (url === "/api/control/history") {
        return Promise.resolve(new Response(JSON.stringify({ items: [] }), { status: 200 }));
      }
      throw new Error(`Unexpected URL: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const view = render(<StrictMode><ControlDashboard /></StrictMode>);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(abortedControlCalls).toBe(1);
    expect(controlCalls).toBe(2);
    expect(maxActiveControlCalls).toBe(1);
    expect(screen.getByTestId("equipment-Весы").className).toContain("equipment--ok");
    expect(screen.getByTestId("equipment-Лидар").className).toContain("equipment--ok");
    expect(screen.getByTestId("equipment-База данных").className).toContain("equipment--ok");
    expect(screen.queryByText("Проверка…")).toBeNull();

    await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
    expect(controlCalls).toBe(3);

    view.unmount();
    await act(async () => { await vi.advanceTimersByTimeAsync(20000); });
    expect(controlCalls).toBe(3);
  });
});
