import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {afterEach,describe,expect,it,vi} from "vitest";
import {MemoryRouter} from "react-router-dom";
import App from "./App";

afterEach(()=>{cleanup();vi.restoreAllMocks();});
describe("laboratory navigation",()=>{
 it("replaces the permanent sidebar with an accessible sections dropdown",async()=>{
  vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(JSON.stringify({items:[],total:0}),{status:200,headers:{"Content-Type":"application/json"}}));
  render(<MemoryRouter initialEntries={["/fuel-quality"]}><App/></MemoryRouter>);
  expect(document.querySelector(".laboratory-sidebar")).toBeNull();
  const button=screen.getByRole("button",{name:/Разделы/});expect(button.getAttribute("aria-expanded")).toBe("false");
  fireEvent.click(button);expect(button.getAttribute("aria-expanded")).toBe("true");
  const menu=screen.getByRole("menu",{name:"Разделы лаборатории"});
  const links=Array.from(menu.querySelectorAll("a"));expect(links.map(link=>link.textContent)).toEqual(["Журнал плотности","Новое исследование","Справочники","Контроль топлива"]);
  expect(screen.getByRole("menuitem",{name:"Контроль топлива"}).getAttribute("aria-current")).toBe("page");
  fireEvent.click(screen.getByRole("menuitem",{name:"Справочники"}));
  await waitFor(()=>expect(screen.getByRole("heading",{name:"Справочники"})).toBeTruthy());
  expect(screen.queryByRole("menu",{name:"Разделы лаборатории"})).toBeNull();
  fireEvent.click(button);fireEvent.keyDown(document,{key:"Escape"});expect(screen.queryByRole("menu",{name:"Разделы лаборатории"})).toBeNull();
 });

 it("keeps the existing density route available",()=>{
  vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(JSON.stringify({items:[],total:0}),{status:200,headers:{"Content-Type":"application/json"}}));
  render(<MemoryRouter initialEntries={["/experiments"]}><App/></MemoryRouter>);
  expect(screen.getByRole("heading",{name:"Журнал лаборатории"})).toBeTruthy();
  expect(screen.getByRole("link",{name:"Насыпная плотность"})).toBeTruthy();
 });
});
