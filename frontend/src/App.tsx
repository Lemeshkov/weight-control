// frontend/src/App.tsx
import React, { useState, useEffect } from "react";
import axios from "axios";
import { CurrentWeight } from "./components/Weighing/CurrentWeight";
import LidarViewer from "./components/Weighing/LidarViewer";

function App() {
  const [health, setHealth] = useState<any>(null);
  const [weight, setWeight] = useState(0);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<"weighing" | "lidar">("weighing");

  useEffect(() => {
    // Проверка здоровья бэкенда
    axios
      .get("http://localhost:8000/api/health")
      .then((res) => setHealth(res.data))
      .catch((err) => console.error("Health check error:", err));

    // Получение текущего веса
    axios
      .get("http://localhost:8000/api/weighing/current")
      .then((res) => setWeight(res.data.weight))
      .catch((err) => console.error("Weight fetch error:", err));
  }, []);

  const startWeighing = async () => {
    setLoading(true);
    try {
      await axios.post("http://localhost:8000/api/weighing/start-trip");
      alert("Взвешивание начато");
      const response = await axios.get(
        "http://localhost:8000/api/weighing/current",
      );
      setWeight(response.data.weight);
    } catch (error) {
      console.error("Error starting weighing:", error);
      alert("Ошибка при начале взвешивания");
    }
    setLoading(false);
  };

  return (
    <div style={{ padding: 20, fontFamily: "Arial, sans-serif" }}>
      <h1> Weight Control System - Уголь-Контроль</h1>

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
            transition: "all 0.3s",
          }}
        >
          🚛 Весовой контроль
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
            transition: "all 0.3s",
          }}
        >
          📡 Лидарный контроль
        </button>
      </div>

      {/* Контент вкладок */}
      {activeTab === "weighing" && (
        <>
          <div
            style={{
              background: "#f0f0f0",
              padding: 15,
              borderRadius: 8,
              marginBottom: 20,
            }}
          >
            <h3 style={{ marginTop: 0 }}>📊 Состояние системы</h3>
            <p>
              <strong>Статус:</strong>{" "}
              {health?.status === "ok"
                ? "✅ Работает"
                : health?.status || "⏳ Проверка..."}
            </p>
            <p>
              <strong>Текущий вес:</strong>{" "}
              <span style={{ fontSize: 20, fontWeight: "bold" }}>{weight}</span>{" "}
              кг
            </p>
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
                marginTop: 10,
              }}
            >
              {loading ? "🔄 Загрузка..." : "🚛 Начать взвешивание"}
            </button>
          </div>

          <hr style={{ margin: "20px 0" }} />

          <CurrentWeight />
        </>
      )}

      {activeTab === "lidar" && <LidarViewer />}
    </div>
  );
}

export default App;
