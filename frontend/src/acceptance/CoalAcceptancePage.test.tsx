import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CoalAcceptancePage } from "./CoalAcceptancePage";

afterEach(() => vi.restoreAllMocks());

describe("coal acceptance workplace", () => {
  it("loads a Trip queue and keeps system fields separate from invoice entry", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url=String(input);
      const body=url.includes("directories") ? {suppliers:[{id:1,name:"Разрез"}],coal_grades:[{id:1,name:"Д"}]} : {items:[{trip_id:10,status:"WAITING",has_warning:false,vehicle:{license_plate:"У211ОО147",model:"КамАЗ"},entry_time:"2026-08-07T07:00:00Z",actual_net_weight_t:31.5,lidar:null,acceptance:null,calculated:{difference_t:null,shortage_t:null,excess_t:null,accepted_weight_t:null}}]};
      return new Response(JSON.stringify(body),{status:200,headers:{"Content-Type":"application/json"}});
    });
    render(<CoalAcceptancePage/>);
    await waitFor(()=>expect(screen.getByText("У211ОО147")).toBeTruthy());
    fireEvent.click(screen.getByText("У211ОО147").closest("tr")!);
    expect(await screen.findByText("Рейс №10")).toBeTruthy();
    expect(screen.getByLabelText("Масса по ТН, т")).toBeTruthy();
    expect(screen.getByText(/Фактический вес: 31.5 т/)).toBeTruthy();
  });
});
