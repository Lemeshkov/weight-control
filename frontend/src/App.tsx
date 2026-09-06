import { useState } from "react";
import "./App.css";
import { ControlDashboard } from "./control/ControlDashboard";
import LidarViewer from "./components/Weighing/LidarViewer";
import { CoalAcceptancePage } from "./acceptance/CoalAcceptancePage";
import { SupplierAdminPage } from "./admin/SupplierAdminPage";
import { AnalyticsPage } from "./analytics/AnalyticsPage";

function App() {
  const [page, setPage] = useState<"control" | "acceptance" | "diagnostics" | "admin" | "analytics">("control");
  const navigate = (next: typeof page) => {
    if (window.dispatchEvent(new CustomEvent("app:navigate", { cancelable: true, detail: next }))) setPage(next);
  };
  return <div className="app-shell">
    <header className="topbar">
      <div><span className="brand-mark">WC</span><div><b>Весовой комплекс</b><small>Рабочее место оператора</small></div></div>
      <nav aria-label="Основная навигация">
        <button className={page === "control" ? "active" : ""} onClick={() => navigate("control")}>Контроль проезда</button>
        <button className={page === "acceptance" ? "active" : ""} onClick={() => navigate("acceptance")}>Приёмка угля</button>
        <button className={page === "diagnostics" ? "active" : ""} onClick={() => navigate("diagnostics")}>Диагностика лидара</button>
        <button className={page === "admin" ? "active" : ""} onClick={() => navigate("admin")}>Администрирование</button>
        <button className={page === "analytics" ? "active" : ""} onClick={() => navigate("analytics")}>Аналитика</button>
      </nav>
    </header>
    {page === "control" ? <ControlDashboard /> : page === "acceptance" ? <CoalAcceptancePage /> : page === "admin" ? <SupplierAdminPage /> : page === "analytics" ? <AnalyticsPage /> : <div className="diagnostics"><LidarViewer /></div>}
  </div>;
}
export default App;
