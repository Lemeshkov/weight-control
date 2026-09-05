import {fireEvent,render,screen,waitFor} from "@testing-library/react";
import {beforeEach,expect,test,vi} from "vitest";
import {SupplierAdminPage} from "./SupplierAdminPage";

const supplier={id:1,name:"ООО Тест",is_active:true};
const grade={id:2,code:"Гр",name:"Гр",description:"Газовый рядовой",is_active:true};
const page=(items:any[])=>({items,total:items.length,page:1,page_size:20,total_pages:items.length?1:0});
beforeEach(()=>{vi.restoreAllMocks();vi.stubGlobal("confirm",vi.fn(()=>true))});

test("dynamic coal-grade tab creates a grade",async()=>{const fetchMock=vi.fn(async(input:any,init?:RequestInit)=>{const url=String(input);if(init?.method==="POST")return {ok:true,status:201,json:async()=>grade};if(url.includes("coal-grades"))return {ok:true,status:200,json:async()=>page([grade])};if(url.includes("suppliers"))return {ok:true,status:200,json:async()=>page([supplier])};return {ok:true,status:200,json:async()=>page([])}});vi.stubGlobal("fetch",fetchMock);render(<SupplierAdminPage/>);fireEvent.click(screen.getByRole("button",{name:"Марки угля"}));await waitFor(()=>expect(screen.getByText("Газовый рядовой")).toBeTruthy());fireEvent.change(screen.getByLabelText("Марка угля *"),{target:{value:"Д"}});fireEvent.click(screen.getByRole("button",{name:"Добавить"}));await waitFor(()=>expect(fetchMock).toHaveBeenCalledWith("/api/admin/coal-grades",expect.objectContaining({method:"POST"})))});

test("supplier deletion requires confirmation",async()=>{const fetchMock=vi.fn(async(_input:any,init?:RequestInit)=>({ok:true,status:init?.method==="DELETE"?204:200,json:async()=>page([supplier])}));vi.stubGlobal("fetch",fetchMock);render(<SupplierAdminPage/>);await waitFor(()=>expect(screen.getByText("ООО Тест")).toBeTruthy());fireEvent.click(screen.getByRole("button",{name:"Удалить"}));expect(confirm).toHaveBeenCalled();await waitFor(()=>expect(fetchMock).toHaveBeenCalledWith("/api/admin/suppliers/1",{method:"DELETE"}))});

test("blocked supplier deletion is human readable",async()=>{vi.stubGlobal("fetch",vi.fn(async(input:any,init?:RequestInit)=>init?.method==="DELETE"?{ok:false,status:409,json:async()=>({detail:{message:"Поставщик используется",references:{vehicles:1,coal_specs:2,laboratory_records:3}}})}:{ok:true,status:200,json:async()=>String(input).includes("suppliers")?page([supplier]):page([])}));render(<SupplierAdminPage/>);await waitFor(()=>screen.getByText("ООО Тест"));fireEvent.click(screen.getByRole("button",{name:"Удалить"}));await waitFor(()=>expect(screen.getByText(/Машины: 1/)).toBeTruthy())});
