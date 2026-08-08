import {useEffect,useRef,useState,type ReactNode} from "react";
import {NavLink} from "react-router-dom";
import {labApi} from "../api";

const sections=[
 {to:"/experiments",label:"Журнал плотности",end:true},
 {to:"/experiments/new",label:"Новое исследование",end:true},
 {to:"/directories",label:"Справочники",end:true},
 {to:"/fuel-quality",label:"Контроль топлива",end:true},
];

export function AppShell({children}:{children:ReactNode}){
 const [online,setOnline]=useState(false),[menuOpen,setMenuOpen]=useState(false);const menuRef=useRef<HTMLDivElement>(null);
 useEffect(()=>{labApi.health().then(()=>setOnline(true)).catch(()=>setOnline(false));},[]);
 useEffect(()=>{if(!menuOpen)return;const closeOutside=(event:MouseEvent)=>{if(!menuRef.current?.contains(event.target as Node))setMenuOpen(false);};const closeEscape=(event:KeyboardEvent)=>{if(event.key==="Escape")setMenuOpen(false);};document.addEventListener("mousedown",closeOutside);document.addEventListener("keydown",closeEscape);return()=>{document.removeEventListener("mousedown",closeOutside);document.removeEventListener("keydown",closeEscape);};},[menuOpen]);
 return <div className="laboratory-shell"><header className="laboratory-topbar"><div className="laboratory-brand"><span className="brand-mark">ЛМ</span><div><strong>Лабораторный модуль</strong><small>Независимый контур контроля угля</small></div></div><div className="topbar-actions"><div className="section-menu" ref={menuRef}><button type="button" className="section-menu-button" aria-haspopup="menu" aria-expanded={menuOpen} aria-controls="laboratory-sections" onClick={()=>setMenuOpen(value=>!value)}>Разделы <span aria-hidden="true">▾</span></button>{menuOpen&&<div id="laboratory-sections" className="section-menu-popover" role="menu" aria-label="Разделы лаборатории">{sections.map(section=><NavLink key={section.to} to={section.to} end={section.end} role="menuitem" onClick={()=>setMenuOpen(false)}>{section.label}</NavLink>)}</div>}</div><div className="service-pill"><i className={online?"online":"offline"}/>{online?"API :8001 доступен":"API :8001 недоступен"}</div></div></header><nav className="process-nav" aria-label="Лабораторные процессы"><NavLink to="/experiments">Насыпная плотность</NavLink><NavLink to="/fuel-quality">Ежесуточный контроль топлива</NavLink></nav><main className="laboratory-body content">{children}</main></div>;
}
