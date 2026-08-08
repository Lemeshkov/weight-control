import {render,screen} from "@testing-library/react";
import {afterEach,describe,expect,it,vi} from "vitest";
import {MemoryRouter} from "react-router-dom";
import App from "./App";

afterEach(()=>{vi.restoreAllMocks();});
describe("laboratory navigation",()=>{
 it("keeps bulk density and fuel quality in the same laboratory frontend",()=>{
  vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(JSON.stringify({items:[],total:0}),{status:200,headers:{"Content-Type":"application/json"}}));
  render(<MemoryRouter initialEntries={["/fuel-quality"]}><App/></MemoryRouter>);
  expect(screen.getByRole("link",{name:"Насыпная плотность"})).toBeTruthy();
  expect(screen.getByRole("link",{name:"Ежесуточный контроль топлива"})).toBeTruthy();
  expect(screen.getByRole("heading",{name:"Контроль топлива"})).toBeTruthy();
 });
});
