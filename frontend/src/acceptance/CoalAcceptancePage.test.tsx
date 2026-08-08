import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CoalAcceptancePage } from "./CoalAcceptancePage";

const queueItem = {trip_id:10,status:"WAITING",has_warning:false,vehicle:{license_plate:"У211ОО147",model:"КамАЗ"},entry_time:"2026-08-07T07:00:00Z",exit_time:null,brutto_weight_kg:35500,tare_weight_kg:4000,actual_net_weight_t:31.5,lidar:null,acceptance:null,calculated:{difference_t:null,allowed_difference_t:null,shortage_t:null,excess_t:null,accepted_weight_t:null}};

afterEach(() => vi.restoreAllMocks());

describe("coal acceptance workplace", () => {
  it("renders queue, system data, required progress and comma mass input", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async input => {
      const body=String(input).includes("directories") ? {suppliers:[{id:1,name:"Разрез"}],coal_grades:[{id:1,name:"Д"}]} : {items:[queueItem],total:1,page:1,page_size:25};
      return new Response(JSON.stringify(body),{status:200,headers:{"Content-Type":"application/json"}});
    });
    render(<CoalAcceptancePage/>);
    await waitFor(()=>expect(screen.getByText("У211ОО147")).toBeTruthy());
    fireEvent.click(screen.getByText("У211ОО147").closest("tr")!);
    expect(await screen.findByText("Рейс №10")).toBeTruthy();
    const mass=screen.getByLabelText(/Масса по ТН, т/) as HTMLInputElement;
    fireEvent.change(mass,{target:{value:"31,520"}});
    expect(mass.value).toBe("31.520");
    expect(screen.getAllByText("31.500 т").length).toBeGreaterThan(0);
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("1");
    expect((screen.getByRole("button",{name:"Завершить оформление"}) as HTMLButtonElement).disabled).toBe(true);
  });
});
