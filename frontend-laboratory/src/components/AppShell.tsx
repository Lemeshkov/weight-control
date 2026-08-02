import { useEffect, useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { labApi } from "../api";

export function AppShell({ children }: { children: ReactNode }) {
  const [online, setOnline] = useState(false);
  useEffect(() => { labApi.health().then(() => setOnline(true)).catch(() => setOnline(false)); }, []);
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">ЛУ</span><div><strong>Лаборатория</strong><small>контроль угля</small></div></div>
      <nav>
        <NavLink to="/experiments"><span>Ж</span>Журнал</NavLink>
        <NavLink to="/experiments/new"><span>+</span>Новое исследование</NavLink>
        <NavLink to="/directories"><span>С</span>Справочники</NavLink>
      </nav>
      <div className="sidebar-status"><i className={online ? "online" : "offline"} />{online ? "API доступен" : "API недоступен"}</div>
    </aside>
    <div className="workspace">
      <header className="topbar"><div><strong>Лабораторный модуль</strong><span>Насыпная плотность угля</span></div><div className="service-pill">Независимый контур</div></header>
      <main className="content">{children}</main>
    </div>
  </div>;
}
