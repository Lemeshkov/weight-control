import {fireEvent,render,screen,waitFor} from "@testing-library/react";
import {expect,test,vi} from "vitest";
import {AnalyticsPage} from "./AnalyticsPage";

const report={filters:{date_from:"2026-09-01",date_to:"2026-09-05",supplier_id:null},rows:[{supplier_id:1,supplier_name:"ООО ТТК",trip_count:2,total_weight_t:"41.500",total_volume_m3:null,bulk_density_t_m3:null}],totals:{trip_count:2,total_weight_t:"41.500",total_volume_m3:null,bulk_density_t_m3:null}};
const suppliers={items:[{id:1,name:"ООО ТТК",is_active:false}],total:1,page:1,page_size:100,total_pages:1};
const mockFetch=(value:any=report,ok=true)=>vi.fn(async(input:any)=>({ok,json:async()=>String(input).includes("suppliers")?suppliers:value}));

test("renders analytics report, totals and unavailable values",async()=>{vi.stubGlobal("fetch",mockFetch());render(<AnalyticsPage/>);expect(screen.getByRole("heading",{name:"Аналитика"})).toBeTruthy();await waitFor(()=>expect(screen.getAllByText("ООО ТТК").length).toBeGreaterThan(1));expect(screen.getByText("ИТОГО")).toBeTruthy();expect(screen.getAllByText("—").length).toBeGreaterThan(1)});

test("apply and Excel use selected dates and supplier",async()=>{const fetchMock=mockFetch();const open=vi.fn();vi.stubGlobal("fetch",fetchMock);vi.stubGlobal("open",open);render(<AnalyticsPage/>);await waitFor(()=>expect(screen.getAllByText("ООО ТТК").length).toBeGreaterThan(1));fireEvent.change(screen.getByLabelText("Дата с"),{target:{value:"2026-09-01"}});fireEvent.change(screen.getByLabelText("Дата по"),{target:{value:"2026-09-05"}});fireEvent.change(screen.getByLabelText("Поставщик"),{target:{value:"1"}});fireEvent.click(screen.getByRole("button",{name:"Применить"}));await waitFor(()=>expect(fetchMock.mock.calls.some(([url])=>String(url).includes("supplier_id=1"))).toBe(true));fireEvent.click(screen.getByRole("button",{name:"Выгрузить Excel"}));expect(open).toHaveBeenCalledWith(expect.stringMatching(/date_from=2026-09-01.*date_to=2026-09-05.*supplier_id=1/),"_self")});

test("reset, empty and error states are controlled",async()=>{const fetchMock=mockFetch({...report,rows:[],totals:{...report.totals,trip_count:0,total_weight_t:"0.000"}});vi.stubGlobal("fetch",fetchMock);render(<AnalyticsPage/>);await waitFor(()=>screen.getByText("За выбранный период данные отсутствуют"));fireEvent.click(screen.getByRole("button",{name:"Сбросить"}));expect((screen.getByLabelText("Поставщик") as HTMLSelectElement).value).toBe("")});

test("API failure is shown",async()=>{vi.stubGlobal("fetch",mockFetch(report,false));render(<AnalyticsPage/>);await waitFor(()=>screen.getByText("Не удалось сформировать отчёт"))});
