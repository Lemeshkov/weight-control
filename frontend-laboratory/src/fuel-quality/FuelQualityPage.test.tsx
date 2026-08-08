import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {afterEach,describe,expect,it,vi} from "vitest";
import {DEFAULT_SPLIT_RATIO,FuelQualityPage} from "./FuelQualityPage";

afterEach(()=>{cleanup();localStorage.clear();vi.restoreAllMocks();});
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

 it("marks a legacy Excel row and does not render missing raw inputs",async()=>{
  const item={id:1,sample_date:"2026-07-01",sample_name:"Ежесуточный контроль 01.07.2026",calorimeter:null,
   status:"COMPLETED",source:"LEGACY_EXCEL",source_file:"Ежесуточный контроль топлива 2026.xlsx",source_sheet:"07",
   updated_at:"2026-08-08T00:00:00Z",wr_percent:"11.99",wa_percent:"2.06",aa_percent:"11.72",sa_percent:"0.37",va_percent:"33.88",
   calculated:{wr_percent:"11.99",wa_percent:"2.06",aa_percent:"11.72",ar_percent:"10.53",ad_percent:"11.97",va_percent:"33.88",vdaf_percent:"39.29",vr_percent:"30.44",sa_percent:"0.37",sr_percent:"0.33",sd_percent:"0.38",qi_r_kcal_kg:"5910"}};
  vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(JSON.stringify({items:[item],total:1}),{status:200,headers:{"Content-Type":"application/json"}}));
 render(<FuelQualityPage/>);
  const scrollTo=vi.spyOn(window,"scrollTo");
  const badge=await screen.findByText("Импорт Excel");fireEvent.click(badge.closest("tr")!);
  const note=screen.getByText("Исходные данные отсутствуют — исторический импорт");
  expect(note.closest("section")?.querySelector("input")).toBeNull();
  expect(screen.getByTestId("fuel-analyses")).toBeTruthy();expect(screen.getByTestId("fuel-detail")).toBeTruthy();
  expect(badge.closest("tr")?.classList.contains("is-selected")).toBe(true);
  expect(screen.getByRole("heading",{name:"Ежесуточный контроль 01.07.2026"})).toBeTruthy();
  expect(scrollTo).not.toHaveBeenCalled();
 });

 it("resizes the split with pointer events and clamps it to 25–70 percent",()=>{
  vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(JSON.stringify({items:[],total:0}),{status:200,headers:{"Content-Type":"application/json"}}));
  render(<FuelQualityPage/>);const separator=screen.getByRole("separator");const work=separator.parentElement!;
  expect(separator.getAttribute("aria-valuenow")).toBe(String(DEFAULT_SPLIT_RATIO));expect(work.style.gridTemplateColumns).toContain("62fr");
  vi.spyOn(work,"getBoundingClientRect").mockReturnValue({left:0,width:1000,top:0,right:1000,bottom:600,height:600,x:0,y:0,toJSON:()=>({})});
  fireEvent.pointerDown(separator,{pointerId:1});fireEvent(separator,new MouseEvent("pointermove",{bubbles:true,clientX:900}));
  expect(separator.getAttribute("aria-valuenow")).toBe("70");expect(localStorage.getItem("laboratory:fuel-quality:split-ratio")).toBe("70");
  fireEvent(separator,new MouseEvent("pointermove",{bubbles:true,clientX:100}));fireEvent.pointerUp(separator,{pointerId:1});
  expect(separator.getAttribute("aria-valuenow")).toBe("25");
 });

 it("restores, changes by keyboard and resets the split to 62 percent",()=>{
  vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(JSON.stringify({items:[],total:0}),{status:200,headers:{"Content-Type":"application/json"}}));
  localStorage.setItem("laboratory:fuel-quality:split-ratio","66");const view=render(<FuelQualityPage/>);let separator=screen.getByRole("separator");
  expect(separator.getAttribute("aria-valuenow")).toBe("66");fireEvent.keyDown(separator,{key:"ArrowLeft"});expect(separator.getAttribute("aria-valuenow")).toBe("64");
  view.unmount();render(<FuelQualityPage/>);separator=screen.getByRole("separator");expect(separator.getAttribute("aria-valuenow")).toBe("64");
  fireEvent.doubleClick(separator);expect(separator.getAttribute("aria-valuenow")).toBe("62");expect(localStorage.getItem("laboratory:fuel-quality:split-ratio")).toBe("62");
  cleanup();localStorage.setItem("laboratory:fuel-quality:split-ratio","invalid");render(<FuelQualityPage/>);expect(screen.getByRole("separator").getAttribute("aria-valuenow")).toBe("62");
 });
});
