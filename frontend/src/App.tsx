// // frontend/src/App.tsx
// import React, { useState, useEffect } from "react";
// import axios from "axios";
// // import { CurrentWeight } from "./components/Weighing/CurrentWeight";
// import LidarViewer from "./components/Weighing/LidarViewer";

// function App() {
//   const [health, setHealth] = useState<any>(null);
//   const [weight, setWeight] = useState(0);
//   const [loading, setLoading] = useState(false);
//   const [activeTab, setActiveTab] = useState<"weighing" | "lidar">("weighing");

//   useEffect(() => {
//     // Проверка здоровья бэкенда
//     axios
//       .get("http://localhost:8000/api/health")
//       .then((res) => setHealth(res.data))
//       .catch((err) => console.error("Health check error:", err));

//     // Получение текущего веса
//     axios
//       .get("http://localhost:8000/api/weighing/current")
//       .then((res) => setWeight(res.data.weight))
//       .catch((err) => console.error("Weight fetch error:", err));
//   }, []);

//   const startWeighing = async () => {
//     setLoading(true);
//     try {
//       await axios.post("http://localhost:8000/api/weighing/start-trip");
//       alert("Взвешивание начато");
//       const response = await axios.get(
//         "http://localhost:8000/api/weighing/current",
//       );
//       setWeight(response.data.weight);
//     } catch (error) {
//       console.error("Error starting weighing:", error);
//       alert("Ошибка при начале взвешивания");
//     }
//     setLoading(false);
//   };

//   return (
//     <div style={{ padding: 20, fontFamily: "Arial, sans-serif" }}>
//       <h1> Weight Control System - Уголь-Контроль</h1>

//       {/* Вкладки */}
//       <div
//         style={{
//           display: "flex",
//           gap: 10,
//           marginBottom: 20,
//           borderBottom: "1px solid #ddd",
//           paddingBottom: 10,
//         }}
//       >
//         <button
//           onClick={() => setActiveTab("weighing")}
//           style={{
//             padding: "10px 20px",
//             fontSize: 16,
//             backgroundColor: activeTab === "weighing" ? "#007bff" : "#f0f0f0",
//             color: activeTab === "weighing" ? "white" : "#333",
//             border: "none",
//             borderRadius: 5,
//             cursor: "pointer",
//             transition: "all 0.3s",
//           }}
//         >
//            Весовой контроль
//         </button>
//         <button
//           onClick={() => setActiveTab("lidar")}
//           style={{
//             padding: "10px 20px",
//             fontSize: 16,
//             backgroundColor: activeTab === "lidar" ? "#007bff" : "#f0f0f0",
//             color: activeTab === "lidar" ? "white" : "#333",
//             border: "none",
//             borderRadius: 5,
//             cursor: "pointer",
//             transition: "all 0.3s",
//           }}
//         >
//            Лидарный контроль
//         </button>
//       </div>

//       {/* Контент вкладок */}
//       {activeTab === "weighing" && (
//         <>
//           <div
//             style={{
//               background: "#f0f0f0",
//               padding: 15,
//               borderRadius: 8,
//               marginBottom: 20,
//             }}
//           >
//             <h3 style={{ marginTop: 0 }}>📊 Состояние системы</h3>
//             <p>
//               <strong>Статус:</strong>{" "}
//               {health?.status === "ok"
//                 ? "✅ Работает"
//                 : health?.status || "⏳ Проверка..."}
//             </p>
//             <p>
//               <strong>Текущий вес:</strong>{" "}
//               <span style={{ fontSize: 20, fontWeight: "bold" }}>{weight}</span>{" "}
//               кг
//             </p>
//             <button
//               onClick={startWeighing}
//               disabled={loading}
//               style={{
//                 padding: "10px 20px",
//                 fontSize: 16,
//                 backgroundColor: "#28a745",
//                 color: "white",
//                 border: "none",
//                 borderRadius: 5,
//                 cursor: loading ? "not-allowed" : "pointer",
//                 marginTop: 10,
//               }}
//             >
//               {loading ? "🔄 Загрузка..." : "🚛 Начать взвешивание"}
//             </button>
//           </div>

//           <hr style={{ margin: "20px 0" }} />

//           {/* <CurrentWeight /> */}
//         </>
//       )}

//       {activeTab === "lidar" && <LidarViewer />}
//     </div>
//   );
// }

// export default App;

// frontend/src/App.tsx
import React, { useState, useEffect } from "react";
import axios from "axios";
import { WeighingHistory } from "./components/Weighing/WeighingHistory";
import LidarViewer from "./components/Weighing/LidarViewer";

function App() {
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<"weighing" | "lidar">("weighing");

  useEffect(() => {
    // Проверка здоровья бэкенда
    axios
      .get("http://localhost:8000/api/health")
      .then((res) => setHealth(res.data))
      .catch((err) => console.error("Health check error:", err));
  }, []);

  const startWeighing = async () => {
    setLoading(true);
    try {
      await axios.post("http://localhost:8000/api/weighing/start-trip");
      alert("✅ Рейс начат!");
      // Обновим историю через перезагрузку страницы
      window.location.reload();
    } catch (error: any) {
      console.error("Error starting weighing:", error);
      const detail = error.response?.data?.detail || "Ошибка при начале рейса";
      alert(`❌ ${detail}`);
    }
    setLoading(false);
  };

  const endWeighing = async () => {
    const id = prompt('Введите ID рейса для завершения:');
    if (!id) return;
    
    setLoading(true);
    try {
      const response = await axios.post(`http://localhost:8000/api/weighing/end-trip/${id}`);
      alert(`✅ Рейс завершен! Нетто: ${response.data.net_weight} кг`);
      window.location.reload();
    } catch (error: any) {
      console.error("Error ending weighing:", error);
      const detail = error.response?.data?.detail || "Ошибка при завершении рейса";
      alert(`❌ ${detail}`);
    }
    setLoading(false);
  };

  return (
    <div style={{ padding: 20, fontFamily: "Arial, sans-serif" }}>
      <h1> Weight Control System</h1>

      {/* Вкладки */}
      <div
        style={{
          display: "flex",
          gap: 10,
          marginBottom: 20,
          borderBottom: "1px solid #ddd",
          paddingBottom: 10,
        }}
      >
        <button
          onClick={() => setActiveTab("weighing")}
          style={{
            padding: "10px 20px",
            fontSize: 16,
            backgroundColor: activeTab === "weighing" ? "#007bff" : "#f0f0f0",
            color: activeTab === "weighing" ? "white" : "#333",
            border: "none",
            borderRadius: 5,
            cursor: "pointer",
          }}
        >
           Весовой контроль
        </button>
        <button
          onClick={() => setActiveTab("lidar")}
          style={{
            padding: "10px 20px",
            fontSize: 16,
            backgroundColor: activeTab === "lidar" ? "#007bff" : "#f0f0f0",
            color: activeTab === "lidar" ? "white" : "#333",
            border: "none",
            borderRadius: 5,
            cursor: "pointer",
          }}
        >
           Лидарный контроль
        </button>
      </div>

      {/* Контент вкладок */}
      {activeTab === "weighing" && (
        <>
          {/* Блок управления */}
          <div
            style={{
              background: "#f0f0f0",
              padding: 20,
              borderRadius: 8,
              marginBottom: 20,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: 10,
            }}
          >
            <div>
              <h3 style={{ margin: 0 }}> Управление рейсами</h3>
              <p style={{ margin: "5px 0 0 0", fontSize: 14, color: "#666" }}>
                Статус: {health?.status === "ok" ? "✅ Система работает" : "⏳ Проверка..."}
              </p>
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <button
                onClick={startWeighing}
                disabled={loading}
                style={{
                  padding: "10px 20px",
                  fontSize: 16,
                  backgroundColor: "#28a745",
                  color: "white",
                  border: "none",
                  borderRadius: 5,
                  cursor: loading ? "not-allowed" : "pointer",
                }}
              >
                {loading ? "🔄 Загрузка..." : " Начать рейс"}
              </button>
              <button
                onClick={endWeighing}
                disabled={loading}
                style={{
                  padding: "10px 20px",
                  fontSize: 16,
                  backgroundColor: "#dc3545",
                  color: "white",
                  border: "none",
                  borderRadius: 5,
                  cursor: loading ? "not-allowed" : "pointer",
                }}
              >
                {loading ? "🔄 Загрузка..." : "⏹ Завершить рейс"}
              </button>
            </div>
          </div>

          {/* История взвешиваний */}
          <WeighingHistory />
        </>
      )}

      {activeTab === "lidar" && <LidarViewer />}
    </div>
  );
}

export default App;