import {fireEvent,render,screen,waitFor} from "@testing-library/react";
import {afterEach,describe,expect,it,vi} from "vitest";
import {FuelQualityPage} from "./FuelQualityPage";

afterEach(()=>{vi.restoreAllMocks();});
describe("fuel quality process",()=>{
 it("creates a draft form and previews the PDF calculation",async()=>{
  vi.spyOn(globalThis,"fetch").mockImplementation(async input=>String(input).includes("calculate")
   ?new Response(JSON.stringify({ar_percent:"10.53",ad_percent:"11.97",vdaf_percent:"39.29",vr_percent:"30.44",sr_percent:"0.33",sd_percent:"0.38",qi_r_kcal_kg:"5910.18"}),{status:200,headers:{"Content-Type":"application/json"}})
   :new Response(JSON.stringify({items:[],total:0}),{status:200,headers:{"Content-Type":"application/json"}}));
  render(<FuelQualityPage/>);fireEvent.click(screen.getByRole("button",{name:"Новый анализ"}));
  const values:Record<string,string>={"Дата пробы":"2026-07-01","Наименование пробы":"Лента 01.07.2026","Sa":"0,37","Wa":"2,06","Aa":"11,72","Wr":"11,99","H (поле PDF)":"5,56","Qb(1)":"6923","Qb(2)":"6924","Va":"33,88","Лаборант":"Шкапорова С.Л."};
  for(const [label,value] of Object.entries(values))fireEvent.change(screen.getByLabelText(new RegExp(label.replace(/[()]/g,"\\$&"))),{target:{value}});
  await waitFor(()=>expect(screen.getAllByText("5910.18").length).toBeGreaterThan(0));
  expect((screen.getByLabelText(/Sa/) as HTMLInputElement).value).toBe("0.37");
  expect((screen.getByRole("button",{name:"Завершить"}) as HTMLButtonElement).disabled).toBe(false);
  expect(screen.getByRole("link",{name:"Экспорт Excel"}).getAttribute("href")).toContain("/api/v1/laboratory/fuel-quality/export.xlsx");
 });
});
