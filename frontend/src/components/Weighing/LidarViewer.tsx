// frontend/src/components/LidarViewer.tsx
import React, { useState, useEffect, useRef } from "react";
import { lidarApi } from "../../services/api";
import axios from "axios";

interface LidarData {
  timestamp: string;
  points_count: number;
  distances_mm: number[];
  distances_m: number[];
  statistics: {
    min_mm: number;
    max_mm: number;
    avg_mm: number;
    min_m: number;
    max_m: number;
    avg_m: number;
  };
}

interface CameraStatus {
  connected: boolean;
  type: string;
  ip?: string;
}

interface VolumeData {
  volume_m3: number;
  cross_section_area: number;
  avg_height_m: number;
  belt_speed_ms: number;
  coal_mass_tons: number;
}

const LidarViewer: React.FC = () => {
  const [lidarData, setLidarData] = useState<LidarData | null>(null);
  const [status, setStatus] = useState<{
    connected: boolean;
    host: string;
    port: number;
  } | null>(null);
  const [cameraStatus, setCameraStatus] = useState<CameraStatus | null>(null);
  const [cameraImage, setCameraImage] = useState<string | null>(null);
  const [volumeData, setVolumeData] = useState<VolumeData | null>(null);
  const [loading, setLoading] = useState(false);
  const [cameraLoading, setCameraLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [showCamera, setShowCamera] = useState(true);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartCanvasRef = useRef<HTMLCanvasElement>(null);
  const intervalRef = useRef<number | undefined>(undefined);

  // Параметры конвейера (можно вынести в настройки)
  const [beltParams, setBeltParams] = useState({
    width_m: 1.5,
    speed_ms: 1.5,
    coal_density_kg_m3: 850, // плотность угля кг/м³
  });

  const fetchStatus = async () => {
    try {
      const response = await lidarApi.getStatus();
      setStatus(response.data);
    } catch (err) {
      console.error("Error fetching lidar status:", err);
    }
  };

  const fetchCameraStatus = async () => {
    try {
      const response = await axios.get(
        "http://localhost:8000/api/camera/status",
      );
      setCameraStatus(response.data);
    } catch (err) {
      console.error("Error fetching camera status:", err);
    }
  };

  const fetchCameraFrame = async () => {
    if (!showCamera) return;
    setCameraLoading(true);
    try {
      const response = await axios.get(
        "http://localhost:8000/api/camera/frame",
        {
          responseType: "blob",
          timeout: 3000,
        },
      );
      const imageUrl = URL.createObjectURL(response.data);
      setCameraImage(imageUrl);
    } catch (err) {
      console.error("Error fetching camera frame:", err);
    } finally {
      setCameraLoading(false);
    }
  };

  const fetchLidarData = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await lidarApi.getScan();
      setLidarData(response.data);

      // Рассчитываем объем угля
      calculateVolume(response.data);

      // Отрисовываем данные на canvas
      if (response.data.distances_mm && response.data.distances_mm.length > 0) {
        drawLidarData(response.data);
        drawDistanceChart(response.data);
      }
    } catch (err: any) {
      console.error("Error fetching lidar data:", err);
      setError(
        err.response?.data?.detail || "Ошибка получения данных с лидара",
      );
    } finally {
      setLoading(false);
    }
  };

  const calculateVolume = (data: LidarData) => {
    if (!data.distances_mm || data.distances_mm.length === 0) return;

    // Расчет площади поперечного сечения угля на конвейере
    const maxDistance = Math.max(...data.distances_mm) / 1000;
    const heights = data.distances_mm.map((d) => maxDistance - d / 1000);

    // Площадь сечения (интеграл по ширине конвейера)
    const step = beltParams.width_m / data.distances_mm.length;
    let crossSectionArea = 0;
    for (let i = 0; i < heights.length - 1; i++) {
      const avgHeight = (heights[i] + heights[i + 1]) / 2;
      crossSectionArea += avgHeight * step;
    }

    // Объем в час
    const volumePerSecond = crossSectionArea * beltParams.speed_ms;
    const volumePerHour = volumePerSecond * 3600;

    // Масса угля (тонны)
    const massPerHour = (volumePerHour * beltParams.coal_density_kg_m3) / 1000;

    setVolumeData({
      volume_m3: Math.round(volumePerHour),
      cross_section_area: Math.round(crossSectionArea * 100) / 100,
      avg_height_m:
        Math.round(
          (heights.reduce((a, b) => a + b, 0) / heights.length) * 100,
        ) / 100,
      belt_speed_ms: beltParams.speed_ms,
      coal_mass_tons: Math.round(massPerHour),
    });
  };

  const drawLidarData = (data: LidarData) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    const centerX = width / 2;
    const centerY = height / 2;
    const maxRadius = Math.min(width, height) / 2 - 20;

    ctx.fillStyle = "#1a1a1a";
    ctx.fillRect(0, 0, width, height);

    if (!data.distances_mm || data.distances_mm.length === 0) {
      ctx.fillStyle = "#ffffff";
      ctx.font = "16px Arial";
      ctx.textAlign = "center";
      ctx.fillText("Нет данных", centerX, centerY);
      return;
    }

    ctx.strokeStyle = "#333333";
    ctx.lineWidth = 1;

    const maxDistance = Math.max(...data.distances_mm) / 1000;
    const maxDisplayDistance = Math.min(maxDistance, 10);

    for (let i = 1; i <= 4; i++) {
      const radius = (i / 4) * maxRadius;
      ctx.beginPath();
      ctx.arc(centerX, centerY, radius, 0, 2 * Math.PI);
      ctx.stroke();

      const distance = ((maxDisplayDistance * i) / 4).toFixed(1);
      ctx.fillStyle = "#666666";
      ctx.font = "12px Arial";
      ctx.fillText(`${distance}м`, centerX + radius - 10, centerY - 5);
    }

    for (let angle = 0; angle < 360; angle += 45) {
      const rad = (angle * Math.PI) / 180;
      const x = centerX + Math.cos(rad) * maxRadius;
      const y = centerY + Math.sin(rad) * maxRadius;
      ctx.beginPath();
      ctx.moveTo(centerX, centerY);
      ctx.lineTo(x, y);
      ctx.stroke();

      const labelX = centerX + Math.cos(rad) * (maxRadius + 10);
      const labelY = centerY + Math.sin(rad) * (maxRadius + 10);
      ctx.fillStyle = "#888888";
      ctx.fillText(`${angle}°`, labelX - 10, labelY);
    }

    const angleStep = (2 * Math.PI) / data.distances_mm.length;
    let startAngle = -Math.PI / 2;

    for (let i = 0; i < data.distances_mm.length; i++) {
      const distanceM = data.distances_mm[i] / 1000;
      if (distanceM > maxDisplayDistance) continue;

      const radius = (distanceM / maxDisplayDistance) * maxRadius;
      const angle = startAngle + i * angleStep;

      const x = centerX + Math.cos(angle) * radius;
      const y = centerY + Math.sin(angle) * radius;

      if (distanceM < 1) {
        ctx.fillStyle = "#ff4444";
      } else if (distanceM < 3) {
        ctx.fillStyle = "#ffaa44";
      } else {
        ctx.fillStyle = "#44ff44";
      }

      ctx.fillRect(x - 2, y - 2, 4, 4);
    }

    ctx.fillStyle = "#ff4444";
    ctx.beginPath();
    ctx.arc(centerX, centerY, 8, 0, 2 * Math.PI);
    ctx.fill();
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 14px Arial";
    ctx.textAlign = "center";
    ctx.fillText("ЛИДАР", centerX, centerY + 4);
  };

  const drawDistanceChart = (data: LidarData) => {
    const canvas = chartCanvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;

    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, width, height);

    if (!data.distances_m || data.distances_m.length === 0) {
      ctx.fillStyle = "#666666";
      ctx.font = "14px Arial";
      ctx.textAlign = "center";
      ctx.fillText("Нет данных для отображения", width / 2, height / 2);
      return;
    }

    const maxDistance = Math.max(...data.distances_m);
    const step = width / data.distances_m.length;

    ctx.strokeStyle = "#e0e0e0";
    ctx.lineWidth = 1;

    for (let i = 0; i <= 4; i++) {
      const y = height - (i / 4) * height;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();

      const distance = ((i / 4) * maxDistance).toFixed(1);
      ctx.fillStyle = "#666666";
      ctx.font = "10px Arial";
      ctx.fillText(`${distance}м`, 5, y - 2);
    }

    ctx.beginPath();
    ctx.strokeStyle = "#007bff";
    ctx.lineWidth = 2;

    for (let i = 0; i < data.distances_m.length; i++) {
      const x = i * step;
      const y = height - (data.distances_m[i] / maxDistance) * height;

      if (i === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.stroke();

    const thresholdY = height - (3 / maxDistance) * height;
    if (thresholdY >= 0 && thresholdY <= height) {
      ctx.beginPath();
      ctx.strokeStyle = "#ff0000";
      ctx.setLineDash([5, 5]);
      ctx.moveTo(0, thresholdY);
      ctx.lineTo(width, thresholdY);
      ctx.stroke();
      ctx.setLineDash([]);

      ctx.fillStyle = "#ff0000";
      ctx.font = "10px Arial";
      ctx.fillText("Порог 3м", width - 60, thresholdY - 2);
    }

    ctx.fillStyle = "#666666";
    ctx.font = "12px Arial";
    ctx.fillText("Номер точки", width / 2 - 40, height - 5);

    ctx.save();
    ctx.translate(15, height / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText("Расстояние (м)", -20, 0);
    ctx.restore();
  };

  useEffect(() => {
    fetchStatus();
    fetchCameraStatus();
    fetchLidarData();
    fetchCameraFrame();

    if (intervalRef.current) {
      clearInterval(intervalRef.current);
    }

    if (autoRefresh) {
      intervalRef.current = window.setInterval(() => {
        fetchLidarData();
        if (showCamera) fetchCameraFrame();
      }, 2000);
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [autoRefresh, showCamera]);

  useEffect(() => {
    if (lidarData && lidarData.distances_mm) {
      drawLidarData(lidarData);
      drawDistanceChart(lidarData);
    }
  }, [lidarData]);

  return (
    <div
      style={{
        padding: "20px",
        backgroundColor: "#f5f5f5",
        borderRadius: "8px",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "20px",
          flexWrap: "wrap",
          gap: "10px",
        }}
      >
        <h2 style={{ margin: 0 }}> Измерение объема угля</h2>
        <div
          style={{
            display: "flex",
            gap: "10px",
            alignItems: "center",
            flexWrap: "wrap",
          }}
        >
          <label style={{ display: "flex", alignItems: "center", gap: "5px" }}>
            <input
              type="checkbox"
              checked={showCamera}
              onChange={(e) => setShowCamera(e.target.checked)}
            />
             Показывать камеру
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "5px" }}>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            Автообновление (2с)
          </label>
          <button
            onClick={fetchLidarData}
            disabled={loading}
            style={{
              padding: "8px 16px",
              backgroundColor: "#007bff",
              color: "white",
              border: "none",
              borderRadius: "4px",
              cursor: loading ? "not-allowed" : "pointer",
            }}
          >
            {loading ? "Загрузка..." : "🔄 Обновить"}
          </button>
        </div>
      </div>

      {/* Статус подключения */}
      <div
        style={{
          marginBottom: "20px",
          display: "flex",
          gap: "20px",
          flexWrap: "wrap",
        }}
      >
        <div
          style={{
            padding: "10px",
            backgroundColor: "white",
            borderRadius: "4px",
            flex: 1,
          }}
        >
          <span> Лидар: </span>
          <span
            style={{
              color: status?.connected ? "#28a745" : "#dc3545",
              fontWeight: "bold",
            }}
          >
            {status?.connected ? " Подключен" : "❌ Не подключен"}
          </span>
          {status && (
            <span style={{ marginLeft: "10px", fontSize: "12px" }}>
              {status.host}:{status.port}
            </span>
          )}
        </div>
        <div
          style={{
            padding: "10px",
            backgroundColor: "white",
            borderRadius: "4px",
            flex: 1,
          }}
        >
          <span> Камера: </span>
          <span
            style={{
              color: cameraStatus?.connected ? "#28a745" : "#dc3545",
              fontWeight: "bold",
            }}
          >
            {cameraStatus?.connected ? " Подключена" : "❌ Не подключена"}
          </span>
          {cameraStatus?.ip && (
            <span style={{ marginLeft: "10px", fontSize: "12px" }}>
              {cameraStatus.ip}
            </span>
          )}
        </div>
      </div>

      {error && (
        <div
          style={{
            marginBottom: "20px",
            padding: "10px",
            backgroundColor: "#f8d7da",
            color: "#721c24",
            borderRadius: "4px",
          }}
        >
          ⚠️ {error}
        </div>
      )}

      {/* Карточка с объемом угля */}
      {volumeData && (
        <div
          style={{
            background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
            padding: "20px",
            borderRadius: "12px",
            color: "white",
            marginBottom: "20px",
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
            gap: "15px",
          }}
        >
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: "12px", opacity: 0.9 }}>Объем угля</div>
            <div style={{ fontSize: "32px", fontWeight: "bold" }}>
              {volumeData.volume_m3} м³/час
            </div>
          </div>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: "12px", opacity: 0.9 }}>Масса угля</div>
            <div style={{ fontSize: "32px", fontWeight: "bold" }}>
              {volumeData.coal_mass_tons} т/час
            </div>
          </div>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: "12px", opacity: 0.9 }}>Сечение угля</div>
            <div style={{ fontSize: "24px", fontWeight: "bold" }}>
              {volumeData.cross_section_area} м²
            </div>
          </div>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: "12px", opacity: 0.9 }}>Ср. высота</div>
            <div style={{ fontSize: "24px", fontWeight: "bold" }}>
              {volumeData.avg_height_m} м
            </div>
          </div>
        </div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: showCamera ? "1fr 1fr" : "1fr",
          gap: "20px",
        }}
      >
        {/* Левая колонка - Лидар */}
        <div>
          <div
            style={{
              backgroundColor: "white",
              borderRadius: "8px",
              padding: "10px",
              marginBottom: "20px",
            }}
          >
            <h3 style={{ marginTop: 0, marginBottom: "15px" }}>
               3D Сканирование конвейера
            </h3>
            <canvas
              ref={canvasRef}
              width={500}
              height={500}
              style={{
                width: "100%",
                maxWidth: "500px",
                height: "auto",
                border: "1px solid #ddd",
                borderRadius: "4px",
                display: "block",
                margin: "0 auto",
              }}
            />
            <div
              style={{
                fontSize: "12px",
                color: "#666",
                marginTop: "10px",
                textAlign: "center",
              }}
            >
              🟢 &gt;3м &nbsp;&nbsp; 🟡 1-3м &nbsp;&nbsp; 🔴 &lt;1м
            </div>
          </div>

          {/* Статистика лидара */}
          {lidarData && lidarData.points_count > 0 && (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(3, 1fr)",
                gap: "10px",
                marginBottom: "20px",
              }}
            >
              <div
                style={{
                  padding: "10px",
                  backgroundColor: "white",
                  borderRadius: "4px",
                  textAlign: "center",
                }}
              >
                <div style={{ fontSize: "11px", color: "#666" }}>Точек</div>
                <div style={{ fontSize: "20px", fontWeight: "bold" }}>
                  {lidarData.points_count}
                </div>
              </div>
              <div
                style={{
                  padding: "10px",
                  backgroundColor: "white",
                  borderRadius: "4px",
                  textAlign: "center",
                }}
              >
                <div style={{ fontSize: "11px", color: "#666" }}>Мин.</div>
                <div style={{ fontSize: "20px", fontWeight: "bold" }}>
                  {lidarData.statistics.min_m}m
                </div>
              </div>
              <div
                style={{
                  padding: "10px",
                  backgroundColor: "white",
                  borderRadius: "4px",
                  textAlign: "center",
                }}
              >
                <div style={{ fontSize: "11px", color: "#666" }}>Макс.</div>
                <div style={{ fontSize: "20px", fontWeight: "bold" }}>
                  {lidarData.statistics.max_m}m
                </div>
              </div>
            </div>
          )}

          {/* График */}
          {lidarData &&
            lidarData.distances_m &&
            lidarData.distances_m.length > 0 && (
              <div
                style={{
                  padding: "15px",
                  backgroundColor: "white",
                  borderRadius: "4px",
                }}
              >
                <h3 style={{ marginTop: 0, marginBottom: "15px" }}>
                   Профиль угля на конвейере
                </h3>
                <canvas
                  ref={chartCanvasRef}
                  width={600}
                  height={200}
                  style={{
                    width: "100%",
                    height: "200px",
                    border: "1px solid #ddd",
                    borderRadius: "4px",
                  }}
                />
                <div
                  style={{ fontSize: "12px", color: "#666", marginTop: "10px" }}
                >
                  🔴 Красная линия - порог 3 метра
                </div>
              </div>
            )}
        </div>

        {/* Правая колонка - Камера */}
        {showCamera && (
          <div>
            <div
              style={{
                backgroundColor: "white",
                borderRadius: "8px",
                padding: "10px",
              }}
            >
              <h3 style={{ marginTop: 0, marginBottom: "15px" }}>
                 Контроль качества
              </h3>
              {cameraLoading && (
                <div style={{ textAlign: "center", padding: "20px" }}>
                  Загрузка кадра...
                </div>
              )}
              {cameraImage && !cameraLoading && (
                <img
                  src={cameraImage}
                  alt="Camera feed"
                  style={{
                    width: "100%",
                    borderRadius: "4px",
                    border: "1px solid #ddd",
                  }}
                />
              )}
              {!cameraImage && !cameraLoading && (
                <div
                  style={{
                    textAlign: "center",
                    padding: "40px",
                    color: "#666",
                    background: "#f9f9f9",
                    borderRadius: "4px",
                  }}
                >
                   Нет изображения с камеры
                  <br />
                  <span style={{ fontSize: "12px" }}>
                    Проверьте подключение камеры
                  </span>
                </div>
              )}
              <div
                style={{
                  fontSize: "12px",
                  color: "#666",
                  marginTop: "10px",
                  textAlign: "center",
                }}
              >
                {cameraStatus?.connected
                  ? "Камера работает"
                  : "Ожидание подключения камеры"}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Время последнего обновления */}
      {lidarData && (
        <div
          style={{
            marginTop: "15px",
            fontSize: "12px",
            color: "#666",
            textAlign: "center",
          }}
        >
          Последнее обновление:{" "}
          {new Date(lidarData.timestamp).toLocaleTimeString()}
        </div>
      )}

      {/* Настройки конвейера */}
      <details style={{ marginTop: "20px" }}>
        <summary style={{ cursor: "pointer", color: "#666", fontSize: "12px" }}>
           Настройки конвейера (для точного расчета объема)
        </summary>
        <div
          style={{
            marginTop: "10px",
            padding: "15px",
            backgroundColor: "white",
            borderRadius: "4px",
          }}
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(3, 1fr)",
              gap: "15px",
            }}
          >
            <div>
              <label style={{ fontSize: "12px", color: "#666" }}>
                Ширина ленты (м)
              </label>
              <input
                type="number"
                step="0.1"
                value={beltParams.width_m}
                onChange={(e) =>
                  setBeltParams({
                    ...beltParams,
                    width_m: parseFloat(e.target.value),
                  })
                }
                style={{ width: "100%", padding: "5px", marginTop: "5px" }}
              />
            </div>
            <div>
              <label style={{ fontSize: "12px", color: "#666" }}>
                Скорость ленты (м/с)
              </label>
              <input
                type="number"
                step="0.1"
                value={beltParams.speed_ms}
                onChange={(e) =>
                  setBeltParams({
                    ...beltParams,
                    speed_ms: parseFloat(e.target.value),
                  })
                }
                style={{ width: "100%", padding: "5px", marginTop: "5px" }}
              />
            </div>
            <div>
              <label style={{ fontSize: "12px", color: "#666" }}>
                Плотность угля (кг/м³)
              </label>
              <input
                type="number"
                step="10"
                value={beltParams.coal_density_kg_m3}
                onChange={(e) =>
                  setBeltParams({
                    ...beltParams,
                    coal_density_kg_m3: parseFloat(e.target.value),
                  })
                }
                style={{ width: "100%", padding: "5px", marginTop: "5px" }}
              />
            </div>
          </div>
          <button
            onClick={() => lidarData && calculateVolume(lidarData)}
            style={{
              marginTop: "10px",
              padding: "5px 10px",
              backgroundColor: "#28a745",
              color: "white",
              border: "none",
              borderRadius: "4px",
              cursor: "pointer",
            }}
          >
            Пересчитать объем
          </button>
        </div>
      </details>
    </div>
  );
};

export default LidarViewer;

