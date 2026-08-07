import { useState } from "react";
import "./App.css";
import { ControlDashboard } from "./control/ControlDashboard";
import LidarViewer from "./components/Weighing/LidarViewer";
import { CoalAcceptancePage } from "./acceptance/CoalAcceptancePage";

function App() {
  const [page, setPage] = useState<"control" | "acceptance" | "diagnostics">("control");
  return <div className="app-shell">
    <header className="topbar">
      <div><span className="brand-mark">WC</span><div><b>Весовой комплекс</b><small>Рабочее место оператора</small></div></div>
      <nav aria-label="Основная навигация">
        <button className={page === "control" ? "active" : ""} onClick={() => setPage("control")}>Контроль проезда</button>
        <button className={page === "acceptance" ? "active" : ""} onClick={() => setPage("acceptance")}>Приёмка угля</button>
        <button className={page === "diagnostics" ? "active" : ""} onClick={() => setPage("diagnostics")}>Диагностика лидара</button>
      </nav>
    </header>
    {page === "control" ? <ControlDashboard /> : page === "acceptance" ? <CoalAcceptancePage /> : <div className="diagnostics"><LidarViewer /></div>}
  </div>;
}

export default App;
