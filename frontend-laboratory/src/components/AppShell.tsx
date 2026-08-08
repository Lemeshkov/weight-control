import {useEffect,useState,type ReactNode} from "react";
import {NavLink} from "react-router-dom";
import {labApi} from "../api";

export function AppShell({children}:{children:ReactNode}){
 const [online,setOnline]=useState(false);
 useEffect(()=>{labApi.health().then(()=>setOnline(true)).catch(()=>setOnline(false));},[]);
 return <div className="laboratory-shell"><header className="laboratory-topbar"><div className="laboratory-brand"><span className="brand-mark">ЛМ</span><div><strong>Лабораторный модуль</strong><small>Независимый контур контроля угля</small></div></div><div className="service-pill"><i className={online?"online":"offline"}/>{online?"API :8001 доступен":"API :8001 недоступен"}</div></header><nav className="process-nav" aria-label="Лабораторные процессы"><NavLink to="/experiments">Насыпная плотность</NavLink><NavLink to="/fuel-quality">Ежесуточный контроль топлива</NavLink></nav><div className="laboratory-body"><aside className="laboratory-sidebar"><NavLink to="/experiments">Журнал плотности</NavLink><NavLink to="/experiments/new">Новое исследование</NavLink><NavLink to="/directories">Справочники</NavLink><NavLink to="/fuel-quality">Контроль топлива</NavLink></aside><main className="content">{children}</main></div></div>;
}
