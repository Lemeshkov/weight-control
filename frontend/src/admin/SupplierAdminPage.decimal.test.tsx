import {fireEvent,render,screen,waitFor} from "@testing-library/react";
import {expect,test,vi} from "vitest";
import {SupplierAdminPage} from "./SupplierAdminPage";

const supplier={id:1,name:"ООО ТТК",is_active:true};
const grade={id:2,code:"Гр",name:"Гр",is_active:true};
const spec={id:12,supplier_id:1,coal_grade_id:2,supplier_name:supplier.name,coal_grade_name:grade.name,calorific_value:"5987.500",calorific_value_unit:"kcal/kg",moisture_pct:"13.500",ash_pct:"15.750",valid_from:"2026-09-01",valid_to:null,is_active:true,fractions:[{fraction_min_mm:"0.000",fraction_max_mm:"5.000",operator:"<=",value:"37.500",unit:"%"}]};
const page=(items:any[])=>({items,total:items.length,page:1,page_size:20,total_pages:items.length?1:0});

function fetcher(){return vi.fn(async(input:any,init?:RequestInit)=>{
 const url=String(input);
 if(init?.method)return {ok:true,status:init.method==="POST"?201:200,json:async()=>spec};
 if(url.includes("/coal-specs?"))return {ok:true,status:200,json:async()=>page([spec])};
 if(url.includes("coal-grades"))return {ok:true,status:200,json:async()=>page([grade])};
 if(url.includes("suppliers"))return {ok:true,status:200,json:async()=>page([supplier])};
 return {ok:true,status:200,json:async()=>page([])}
})}
const bodyOf=(fetchMock:ReturnType<typeof vi.fn>,method:string)=>JSON.parse((fetchMock.mock.calls.find(([,init])=>init?.method===method)?.[1] as RequestInit).body as string);

test("comma decimals are normalized for create without rounding",async()=>{
 const fetchMock=fetcher();vi.stubGlobal("fetch",fetchMock);render(<SupplierAdminPage/>);
 fireEvent.click(screen.getByRole("button",{name:"Характеристики угля"}));await waitFor(()=>screen.getByText("5987.5 kcal/kg"));
 fireEvent.change(screen.getByLabelText("Поставщик"),{target:{value:"1"}});
 fireEvent.change(screen.getByLabelText("Марка угля"),{target:{value:"2"}});
 fireEvent.change(screen.getByLabelText("Калорийность, ккал/кг"),{target:{value:"5987,5"}});
 fireEvent.change(screen.getByLabelText("Влага, %"),{target:{value:"13,5"}});
 fireEvent.change(screen.getByLabelText("Зола, %"),{target:{value:"15,75"}});
 fireEvent.change(screen.getByLabelText("Значение фракции"),{target:{value:"37,5"}});
 fireEvent.click(screen.getByRole("button",{name:"Добавить"}));
 await waitFor(()=>expect(fetchMock.mock.calls.some(([,init])=>init?.method==="POST")).toBe(true));
 expect(bodyOf(fetchMock,"POST")).toMatchObject({calorific_value:"5987.5",moisture_pct:"13.5",ash_pct:"15.75",fractions:[{value:"37.5"}]})
});

test("dot and comma decimals retain precision in PATCH edit",async()=>{
 const fetchMock=fetcher();vi.stubGlobal("fetch",fetchMock);const {container}=render(<SupplierAdminPage/>);
 fireEvent.click(screen.getByRole("button",{name:"Характеристики угля"}));await waitFor(()=>screen.getByText("5987.5 kcal/kg"));
 fireEvent.click(container.querySelector<HTMLButtonElement>("tbody button")!);
 expect((screen.getByLabelText("Влага, %") as HTMLInputElement).value).toBe("13.5");
 fireEvent.change(screen.getByLabelText("Влага, %"),{target:{value:"13,75"}});
 fireEvent.change(screen.getByLabelText("Зола, %"),{target:{value:"15.25"}});
 fireEvent.click(screen.getByRole("button",{name:"Сохранить изменения"}));
 await waitFor(()=>expect(fetchMock).toHaveBeenCalledWith("/api/admin/coal-specs/12",expect.objectContaining({method:"PATCH"})));
 expect(bodyOf(fetchMock,"PATCH")).toMatchObject({moisture_pct:"13.75",ash_pct:"15.25",fractions:[{value:"37.5"}]})
});
