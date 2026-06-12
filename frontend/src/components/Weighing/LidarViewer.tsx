// // frontend/src/components/LidarViewer.tsx (упрощённая версия, только отображение)
// import React, { useState, useEffect, useRef } from "react";
// import { lidarApi } from "../../services/api";
// import axios from "axios";

// interface LidarData {
//   timestamp: string;
//   points_count: number;
//   distances_mm: number[];
//   distances_m: number[];
//   statistics: {
//     min_mm: number;
//     max_mm: number;
//     avg_mm: number;
//     min_m: number;
//     max_m: number;
//     avg_m: number;
//   };
// }

// interface CameraStatus {
//   connected: boolean;
//   type: string;
//   ip?: string;
// }

// interface VolumeData {
//   volume_m3: number;
//   cross_section_area: number;
//   avg_height_m: number;
//   coal_mass_tons: number;
// }

// const LidarViewer: React.FC = () => {
//   const [lidarData, setLidarData] = useState<LidarData | null>(null);
//   const [status, setStatus] = useState<{ connected: boolean; host: string; port: number } | null>(null);
//   const [cameraStatus, setCameraStatus] = useState<CameraStatus | null>(null);
//   const [cameraImage, setCameraImage] = useState<string | null>(null);
//   const [loading, setLoading] = useState(false);
//   const [cameraLoading, setCameraLoading] = useState(false);
//   const [error, setError] = useState<string | null>(null);
//   const [showCamera, setShowCamera] = useState(false); // отключаем камеру
//   const canvasRef = useRef<HTMLCanvasElement>(null);
//   const chartCanvasRef = useRef<HTMLCanvasElement>(null);

//   // Параметры автомобиля
//   const [vehicleParams, setVehicleParams] = useState({
//     length_m: 6.0,
//     width_m: 2.5,
//     coal_density_kg_m3: 850,
//   });

//   const [volumeData, setVolumeData] = useState<VolumeData | null>(null);

//   const fetchStatus = async () => {
//     try {
//       const response = await lidarApi.getStatus();
//       setStatus(response.data);
//     } catch (err) {
//       console.error("Error fetching lidar status:", err);
//     }
//   };

//   const fetchCameraStatus = async () => {
//     if (!showCamera) return;
//     try {
//       const response = await axios.get("http://localhost:8000/api/camera/status");
//       setCameraStatus(response.data);
//     } catch (err) {
//       console.error("Error fetching camera status:", err);
//     }
//   };

//   const fetchCameraFrame = async () => {
//     if (!showCamera) return;
//     setCameraLoading(true);
//     try {
//       const response = await axios.get("http://localhost:8000/api/camera/frame", {
//         responseType: "blob",
//         timeout: 3000,
//       });
//       const imageUrl = URL.createObjectURL(response.data);
//       setCameraImage(imageUrl);
//     } catch (err) {
//       console.error("Error fetching camera frame:", err);
//     } finally {
//       setCameraLoading(false);
//     }
//   };

//   const calculateVolume = (data: LidarData) => {
//     if (!data.distances_mm || data.distances_mm.length < 15) {
//       setVolumeData(null);
//       return;
//     }

//     const roadLevel = Math.max(...data.distances_mm) / 1000;
//     const heights = data.distances_mm.map((d) => {
//       const distM = d / 1000;
//       if (distM < roadLevel - 0.03) return roadLevel - distM;
//       return 0;
//     });

//     const validHeights = heights.filter((h) => h > 0.01);
//     if (validHeights.length === 0) {
//       setVolumeData(null);
//       return;
//     }

//     const avgHeight = validHeights.reduce((a, b) => a + b, 0) / validHeights.length;
//     const calibrationFactor = 60 / (avgHeight * 100);
//     const calibratedHeight = avgHeight * calibrationFactor;
//     const volume_m3 = vehicleParams.length_m * vehicleParams.width_m * calibratedHeight;
//     const mass_tons = (volume_m3 * vehicleParams.coal_density_kg_m3) / 1000;
//     const crossSectionArea = calibratedHeight * vehicleParams.width_m;

//     setVolumeData({
//       volume_m3: Math.round(volume_m3 * 100) / 100,
//       cross_section_area: Math.round(crossSectionArea * 100) / 100,
//       avg_height_m: Math.round(calibratedHeight * 100) / 100,
//       coal_mass_tons: Math.round(mass_tons * 10) / 10,
//     });
//   };

//   const fetchLidarData = async () => {
//     setLoading(true);
//     setError(null);
//     try {
//       const response = await lidarApi.getScan();
//       console.log("📡 Данные получены:", response.data);
//       setLidarData(response.data);
//       calculateVolume(response.data);

//       if (response.data.distances_mm && response.data.distances_mm.length > 0) {
//         drawLidarData(response.data);
//         drawDistanceChart(response.data);
//       }
//     } catch (err: any) {
//       console.error("Error fetching lidar data:", err);
//       setError(err.response?.data?.detail || "Ошибка получения данных с лидара");
//     } finally {
//       setLoading(false);
//     }
//   };

//   const drawLidarData = (data: LidarData) => {
//     const canvas = canvasRef.current;
//     if (!canvas) return;

//     const ctx = canvas.getContext("2d");
//     if (!ctx) return;

//     const width = canvas.width;
//     const height = canvas.height;
//     const centerX = width / 2;
//     const centerY = height / 2;
//     const maxRadius = Math.min(width, height) / 2 - 20;

//     ctx.fillStyle = "#1a1a1a";
//     ctx.fillRect(0, 0, width, height);

//     if (!data.distances_mm || data.distances_mm.length === 0) {
//       ctx.fillStyle = "#ffffff";
//       ctx.font = "16px Arial";
//       ctx.textAlign = "center";
//       ctx.fillText("Нет данных", centerX, centerY);
//       return;
//     }

//     ctx.strokeStyle = "#333333";
//     ctx.lineWidth = 1;

//     const maxDistance = Math.max(...data.distances_mm) / 1000;
//     const maxDisplayDistance = Math.min(maxDistance, 10);

//     for (let i = 1; i <= 4; i++) {
//       const radius = (i / 4) * maxRadius;
//       ctx.beginPath();
//       ctx.arc(centerX, centerY, radius, 0, 2 * Math.PI);
//       ctx.stroke();
//       const distance = ((maxDisplayDistance * i) / 4).toFixed(1);
//       ctx.fillStyle = "#666666";
//       ctx.font = "12px Arial";
//       ctx.fillText(`${distance}м`, centerX + radius - 10, centerY - 5);
//     }

//     const startAngleDeg = -35;
//     const stopAngleDeg = 35;

//     const leftRad = (startAngleDeg * Math.PI) / 180;
//     const leftX = centerX + Math.cos(leftRad) * maxRadius;
//     const leftY = centerY + Math.sin(leftRad) * maxRadius;
//     ctx.beginPath();
//     ctx.moveTo(centerX, centerY);
//     ctx.lineTo(leftX, leftY);
//     ctx.strokeStyle = "#00ff00";
//     ctx.lineWidth = 1;
//     ctx.stroke();

//     const rightRad = (stopAngleDeg * Math.PI) / 180;
//     const rightX = centerX + Math.cos(rightRad) * maxRadius;
//     const rightY = centerY + Math.sin(rightRad) * maxRadius;
//     ctx.beginPath();
//     ctx.moveTo(centerX, centerY);
//     ctx.lineTo(rightX, rightY);
//     ctx.stroke();

//     ctx.beginPath();
//     ctx.arc(centerX, centerY, maxRadius * 0.8, leftRad, rightRad);
//     ctx.strokeStyle = "#00ff00";
//     ctx.setLineDash([5, 5]);
//     ctx.stroke();
//     ctx.setLineDash([]);

//     ctx.fillStyle = "#00ff00";
//     ctx.font = "10px Arial";
//     ctx.fillText(`-35°`, leftX - 15, leftY);
//     ctx.fillText(`+35°`, rightX + 5, rightY - 5);
//     ctx.fillText(`70° сектор`, centerX + 20, centerY - maxRadius * 0.75);

//     for (let angle = -30; angle <= 30; angle += 10) {
//       const rad = (angle * Math.PI) / 180;
//       const x = centerX + Math.cos(rad) * (maxRadius - 10);
//       const y = centerY + Math.sin(rad) * (maxRadius - 10);
//       ctx.beginPath();
//       ctx.moveTo(centerX, centerY);
//       ctx.lineTo(x, y);
//       ctx.strokeStyle = "#444444";
//       ctx.stroke();
//       if (angle !== 0) {
//         ctx.fillStyle = "#666666";
//         ctx.font = "9px Arial";
//         ctx.fillText(`${angle}°`, x, y);
//       }
//     }

//     const sectorAngleDeg = stopAngleDeg - startAngleDeg;
//     const angleStepDeg = sectorAngleDeg / data.distances_mm.length;

//     for (let i = 0; i < data.distances_mm.length; i++) {
//       const distanceM = data.distances_mm[i] / 1000;
//       if (distanceM === 0) continue;
//       if (distanceM > maxDisplayDistance) continue;

//       const currentAngleDeg = startAngleDeg + i * angleStepDeg;
//       const currentAngleRad = (currentAngleDeg * Math.PI) / 180;
//       const radius = (distanceM / maxDisplayDistance) * maxRadius;
//       const x = centerX + Math.cos(currentAngleRad) * radius;
//       const y = centerY + Math.sin(currentAngleRad) * radius;

//       if (distanceM < 1) ctx.fillStyle = "#ff4444";
//       else if (distanceM < 3) ctx.fillStyle = "#ffaa44";
//       else ctx.fillStyle = "#44ff44";

//       ctx.fillRect(x - 2, y - 2, 4, 4);
//     }

//     ctx.fillStyle = "#ff4444";
//     ctx.beginPath();
//     ctx.arc(centerX, centerY, 8, 0, 2 * Math.PI);
//     ctx.fill();
//     ctx.fillStyle = "#ffffff";
//     ctx.font = "bold 14px Arial";
//     ctx.textAlign = "center";
//     ctx.fillText("ЛИДАР", centerX, centerY + 4);

//     ctx.fillStyle = "#888888";
//     ctx.font = "10px Arial";
//     ctx.fillText("Сектор сканирования: 70° (от -35° до +35°)", centerX, height - 10);
//   };

//   const drawDistanceChart = (data: LidarData) => {
//     const canvas = chartCanvasRef.current;
//     if (!canvas) return;

//     const ctx = canvas.getContext("2d");
//     if (!ctx) return;

//     const width = canvas.width;
//     const height = canvas.height;

//     ctx.fillStyle = "#ffffff";
//     ctx.fillRect(0, 0, width, height);

//     if (!data.distances_m || data.distances_m.length === 0) {
//       ctx.fillStyle = "#666666";
//       ctx.font = "14px Arial";
//       ctx.textAlign = "center";
//       ctx.fillText("Нет данных для отображения", width / 2, height / 2);
//       return;
//     }

//     const maxDistance = Math.max(...data.distances_m);
//     const step = width / data.distances_m.length;

//     ctx.strokeStyle = "#e0e0e0";
//     ctx.lineWidth = 1;

//     for (let i = 0; i <= 4; i++) {
//       const y = height - (i / 4) * height;
//       ctx.beginPath();
//       ctx.moveTo(0, y);
//       ctx.lineTo(width, y);
//       ctx.stroke();
//       const distance = ((i / 4) * maxDistance).toFixed(1);
//       ctx.fillStyle = "#666666";
//       ctx.font = "10px Arial";
//       ctx.fillText(`${distance}м`, 5, y - 2);
//     }

//     ctx.beginPath();
//     ctx.strokeStyle = "#007bff";
//     ctx.lineWidth = 2;

//     for (let i = 0; i < data.distances_m.length; i++) {
//       const x = i * step;
//       const y = height - (data.distances_m[i] / maxDistance) * height;
//       if (i === 0) ctx.moveTo(x, y);
//       else ctx.lineTo(x, y);
//     }
//     ctx.stroke();

//     const thresholdY = height - (3 / maxDistance) * height;
//     if (thresholdY >= 0 && thresholdY <= height) {
//       ctx.beginPath();
//       ctx.strokeStyle = "#ff0000";
//       ctx.setLineDash([5, 5]);
//       ctx.moveTo(0, thresholdY);
//       ctx.lineTo(width, thresholdY);
//       ctx.stroke();
//       ctx.setLineDash([]);
//       ctx.fillStyle = "#ff0000";
//       ctx.font = "10px Arial";
//       ctx.fillText("Уровень борта (3м)", width - 120, thresholdY - 2);
//     }

//     ctx.fillStyle = "#666666";
//     ctx.font = "12px Arial";
//     ctx.fillText("Длина кузова", width / 2 - 40, height - 5);

//     ctx.save();
//     ctx.translate(15, height / 2);
//     ctx.rotate(-Math.PI / 2);
//     ctx.fillText("Расстояние до лидара (м)", -20, 0);
//     ctx.restore();
//   };

//   useEffect(() => {
//     fetchStatus();
//     fetchCameraStatus();
//     fetchLidarData();
//     fetchCameraFrame();

//     // Автообновление каждые 2 секунды
//     const interval = setInterval(() => {
//       fetchLidarData();
//     }, 2000);

//     return () => clearInterval(interval);
//   }, []);

//   useEffect(() => {
//     if (lidarData && lidarData.distances_mm) {
//       drawLidarData(lidarData);
//       drawDistanceChart(lidarData);
//     }
//   }, [lidarData]);

//   return (
//     <div style={{ padding: "20px", backgroundColor: "#f5f5f5", borderRadius: "8px" }}>
//       <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px", flexWrap: "wrap", gap: "10px" }}>
//         <h2 style={{ margin: 0 }}>📊 Измерение объема угля в кузове</h2>
//         <div style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" }}>
//           <label style={{ display: "flex", alignItems: "center", gap: "5px" }}>
//             <input type="checkbox" checked={showCamera} onChange={(e) => setShowCamera(e.target.checked)} />
//             📷 Показывать камеру
//           </label>
//           <button onClick={fetchLidarData} disabled={loading} style={{ padding: "8px 16px", backgroundColor: "#007bff", color: "white", border: "none", borderRadius: "4px", cursor: loading ? "not-allowed" : "pointer" }}>
//             {loading ? "Загрузка..." : "🔄 Обновить"}
//           </button>
//         </div>
//       </div>

//       {/* Статус подключения */}
//       <div style={{ marginBottom: "20px", display: "flex", gap: "20px", flexWrap: "wrap" }}>
//         <div style={{ padding: "10px", backgroundColor: "white", borderRadius: "4px", flex: 1 }}>
//           <span>📡 Лидар: </span>
//           <span style={{ color: status?.connected ? "#28a745" : "#dc3545", fontWeight: "bold" }}>
//             {status?.connected ? "✅ Подключен" : "❌ Не подключен"}
//           </span>
//           {status && <span style={{ marginLeft: "10px", fontSize: "12px" }}>{status.host}:{status.port}</span>}
//         </div>
//         <div style={{ padding: "10px", backgroundColor: "white", borderRadius: "4px", flex: 1 }}>
//           <span>📷 Камера: </span>
//           <span style={{ color: cameraStatus?.connected ? "#28a745" : "#dc3545", fontWeight: "bold" }}>
//             {cameraStatus?.connected ? "✅ Подключена" : "❌ Не подключена"}
//           </span>
//         </div>
//       </div>

//       {error && <div style={{ marginBottom: "20px", padding: "10px", backgroundColor: "#f8d7da", color: "#721c24", borderRadius: "4px" }}>⚠️ {error}</div>}

//       {/* Карточка с объемом угля */}
//       {volumeData && (
//         <div style={{
//           background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
//           padding: "20px",
//           borderRadius: "12px",
//           color: "white",
//           marginBottom: "20px",
//           display: "grid",
//           gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
//           gap: "15px",
//         }}>
//           <div style={{ textAlign: "center" }}>
//             <div style={{ fontSize: "12px", opacity: 0.9 }}>Объем угля</div>
//             <div style={{ fontSize: "32px", fontWeight: "bold" }}>{volumeData.volume_m3} м³</div>
//           </div>
//           <div style={{ textAlign: "center" }}>
//             <div style={{ fontSize: "12px", opacity: 0.9 }}>Масса угля</div>
//             <div style={{ fontSize: "32px", fontWeight: "bold" }}>{volumeData.coal_mass_tons} т</div>
//           </div>
//           <div style={{ textAlign: "center" }}>
//             <div style={{ fontSize: "12px", opacity: 0.9 }}>Сечение угля</div>
//             <div style={{ fontSize: "24px", fontWeight: "bold" }}>{volumeData.cross_section_area} м²</div>
//           </div>
//           <div style={{ textAlign: "center" }}>
//             <div style={{ fontSize: "12px", opacity: 0.9 }}>Ср. высота</div>
//             <div style={{ fontSize: "24px", fontWeight: "bold" }}>{volumeData.avg_height_m} м</div>
//           </div>
//         </div>
//       )}

//       <div style={{ display: "grid", gridTemplateColumns: showCamera ? "1fr 1fr" : "1fr", gap: "20px" }}>
//         {/* Левая колонка - Лидар */}
//         <div>
//           <div style={{ backgroundColor: "white", borderRadius: "8px", padding: "10px", marginBottom: "20px" }}>
//             <h3 style={{ marginTop: 0, marginBottom: "15px" }}>🗺️ Сканирование кузова</h3>
//             <canvas ref={canvasRef} width={500} height={500} style={{ width: "100%", maxWidth: "500px", height: "auto", border: "1px solid #ddd", borderRadius: "4px", display: "block", margin: "0 auto" }} />
//             <div style={{ fontSize: "12px", color: "#666", marginTop: "10px", textAlign: "center" }}>
//               🟢 Нормально (&gt;3м) &nbsp;&nbsp; 🟡 Внимание (1-3м) &nbsp;&nbsp; 🔴 Опасно (&lt;1м)
//             </div>
//           </div>

//           {/* Статистика лидара */}
//           {lidarData && lidarData.points_count > 0 && (
//             <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "10px", marginBottom: "20px" }}>
//               <div style={{ padding: "10px", backgroundColor: "white", borderRadius: "4px", textAlign: "center" }}>
//                 <div style={{ fontSize: "11px", color: "#666" }}>Точек</div>
//                 <div style={{ fontSize: "20px", fontWeight: "bold" }}>{lidarData.points_count}</div>
//               </div>
//               <div style={{ padding: "10px", backgroundColor: "white", borderRadius: "4px", textAlign: "center" }}>
//                 <div style={{ fontSize: "11px", color: "#666" }}>Мин. расстояние</div>
//                 <div style={{ fontSize: "20px", fontWeight: "bold" }}>{lidarData.statistics.min_m}м</div>
//               </div>
//               <div style={{ padding: "10px", backgroundColor: "white", borderRadius: "4px", textAlign: "center" }}>
//                 <div style={{ fontSize: "11px", color: "#666" }}>Макс. расстояние</div>
//                 <div style={{ fontSize: "20px", fontWeight: "bold" }}>{lidarData.statistics.max_m}м</div>
//               </div>
//             </div>
//           )}

//           {/* График профиля */}
//           {lidarData && lidarData.distances_m && lidarData.distances_m.length > 0 && (
//             <div style={{ padding: "15px", backgroundColor: "white", borderRadius: "4px" }}>
//               <h3 style={{ marginTop: 0, marginBottom: "15px" }}>📊 Профиль угля в кузове</h3>
//               <canvas ref={chartCanvasRef} width={600} height={200} style={{ width: "100%", height: "200px", border: "1px solid #ddd", borderRadius: "4px" }} />
//               <div style={{ fontSize: "12px", color: "#666", marginTop: "10px" }}>🔴 Красная линия - уровень борта (3 метра от лидара)</div>
//               <div style={{ fontSize: "11px", color: "#888", marginTop: "5px" }}>📌 Выше красной линии - есть уголь, ниже - пустое место</div>
//             </div>
//           )}
//         </div>

//         {/* Правая колонка - Камера */}
//         {showCamera && (
//           <div>
//             <div style={{ backgroundColor: "white", borderRadius: "8px", padding: "10px" }}>
//               <h3 style={{ marginTop: 0, marginBottom: "15px" }}>📸 Контроль качества</h3>
//               {cameraLoading && <div style={{ textAlign: "center", padding: "20px" }}>Загрузка кадра...</div>}
//               {cameraImage && !cameraLoading && <img src={cameraImage} alt="Camera feed" style={{ width: "100%", borderRadius: "4px", border: "1px solid #ddd" }} />}
//               {!cameraImage && !cameraLoading && (
//                 <div style={{ textAlign: "center", padding: "40px", color: "#666", background: "#f9f9f9", borderRadius: "4px" }}>
//                   📷 Нет изображения с камеры
//                 </div>
//               )}
//             </div>
//           </div>
//         )}
//       </div>

//       {/* Настройки автомобиля */}
//       <details style={{ marginTop: "20px" }}>
//         <summary style={{ cursor: "pointer", color: "#666", fontSize: "12px" }}>⚙️ Настройки автомобиля</summary>
//         <div style={{ marginTop: "10px", padding: "15px", backgroundColor: "white", borderRadius: "4px" }}>
//           <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "15px" }}>
//             <div>
//               <label style={{ fontSize: "12px", color: "#666" }}>📏 Длина кузова (м)</label>
//               <input type="number" step="0.5" value={vehicleParams.length_m} onChange={(e) => setVehicleParams({ ...vehicleParams, length_m: parseFloat(e.target.value) })} style={{ width: "100%", padding: "5px", marginTop: "5px" }} />
//             </div>
//             <div>
//               <label style={{ fontSize: "12px", color: "#666" }}>📐 Ширина кузова (м)</label>
//               <input type="number" step="0.1" value={vehicleParams.width_m} onChange={(e) => setVehicleParams({ ...vehicleParams, width_m: parseFloat(e.target.value) })} style={{ width: "100%", padding: "5px", marginTop: "5px" }} />
//             </div>
//             <div>
//               <label style={{ fontSize: "12px", color: "#666" }}>⛏️ Плотность угля (кг/м³)</label>
//               <input type="number" step="10" value={vehicleParams.coal_density_kg_m3} onChange={(e) => setVehicleParams({ ...vehicleParams, coal_density_kg_m3: parseFloat(e.target.value) })} style={{ width: "100%", padding: "5px", marginTop: "5px" }} />
//             </div>
//           </div>
//         </div>
//       </details>
//     </div>
//   );
// };

// export default LidarViewer;

// frontend/src/components/LidarViewer.tsx
import React, { useState, useEffect, useRef } from "react";
import { lidarApi, scan3dApi } from "../../services/api";
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
  coal_mass_tons: number;
}

interface EmptyStatus {
  is_empty: boolean;
  confidence: number;
  reason: string;
  points_count: number;
}

interface ScanProfile {
  timestamp: number;
  position_m: number;
  distances_mm: number[];
  heights_m: number[];
  cross_section_m2: number;
}

interface SavedMeasurement {
  id: number;
  timestamp: string;
  points_count: number;
  volume_m3: number;
  mass_tons: number;
  avg_height_m: number;
  cross_section_m2: number;
  is_empty: boolean;
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
  const [saving, setSaving] = useState(false);
  const [cameraLoading, setCameraLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showCamera, setShowCamera] = useState(false);
  const [measurements, setMeasurements] = useState<SavedMeasurement[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartCanvasRef = useRef<HTMLCanvasElement>(null);
  const [emptyStatus, setEmptyStatus] = useState<EmptyStatus | null>(null);

  // 3D сканирование
  const [isScanning, setIsScanning] = useState(false);
  const [scanProfiles, setScanProfiles] = useState<ScanProfile[]>([]);
  const [totalVolume3d, setTotalVolume3d] = useState<number | null>(null);
  const [scanProgress, setScanProgress] = useState(0);
  const scanIntervalRef = useRef<number | undefined>(undefined);
  const startTimeRef = useRef<number>(0);
  const [currentScanId, setCurrentScanId] = useState<string | null>(null);

  // Параметры автомобиля
  const [vehicleParams, setVehicleParams] = useState({
    length_m: 6.0,
    width_m: 2.5,
    coal_density_kg_m3: 850,
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
      const response = await axios.get("http://localhost:8000/api/camera/status");
      setCameraStatus(response.data);
    } catch (err) {
      console.error("Error fetching camera status:", err);
    }
  };

  const fetchCameraFrame = async () => {
    if (!showCamera) return;
    setCameraLoading(true);
    try {
      const response = await axios.get("http://localhost:8000/api/camera/frame", {
        responseType: "blob",
        timeout: 3000,
      });
      const imageUrl = URL.createObjectURL(response.data);
      setCameraImage(imageUrl);
    } catch (err) {
      console.error("Error fetching camera frame:", err);
    } finally {
      setCameraLoading(false);
    }
  };

  const fetchMeasurements = async () => {
    try {
      const response = await lidarApi.getMeasurements(20);
      setMeasurements(response.data);
    } catch (err) {
      console.error("Error fetching measurements:", err);
    }
  };

  const calculateCrossSection = (distances_mm: number[], roadLevel: number, width_m: number): number => {
    if (!distances_mm.length) return 0;
    const heights = distances_mm.map((d) => {
      const distM = d / 1000;
      if (distM < roadLevel - 0.03) return roadLevel - distM;
      return 0;
    });
    const validHeights = heights.filter((h) => h > 0.01);
    if (validHeights.length === 0) return 0;
    const avgHeight = validHeights.reduce((a, b) => a + b, 0) / validHeights.length;
    return avgHeight * width_m;
  };

  const checkEmptyStatus = (data: LidarData, currentVolume: VolumeData | null) => {
    const pointsCount = data.points_count;
    let is_empty = false;
    let confidence = 0;
    let reason = "";

    if (pointsCount < 15) {
      is_empty = true;
      confidence = 98;
      reason = `Обнаружено слишком мало точек (${pointsCount}) - кузов ПУСТ`;
    } else if (currentVolume && currentVolume.volume_m3 > 0.01) {
      is_empty = false;
      confidence = 98;
      reason = `Обнаружен объём ${currentVolume.volume_m3} м³`;
    } else if (pointsCount < 25) {
      is_empty = true;
      confidence = 85;
      reason = `Мало точек (${pointsCount}) - кузов, вероятно, ПУСТ`;
    } else if (pointsCount < 40) {
      is_empty = false;
      confidence = 75;
      reason = `Обнаружено ${pointsCount} точек - кузов ЗАПОЛНЕН`;
    } else {
      is_empty = false;
      confidence = 95;
      reason = `Обнаружено много точек (${pointsCount}) - кузов ЗАПОЛНЕН`;
    }

    setEmptyStatus({
      is_empty,
      confidence,
      reason,
      points_count: pointsCount,
    });
  };

  const calculateVolume = (data: LidarData) => {
    if (!data.distances_mm || data.distances_mm.length < 15) {
      setVolumeData(null);
      return null;
    }

    const roadLevel = Math.max(...data.distances_mm) / 1000;
    const heights = data.distances_mm.map((d) => {
      const distM = d / 1000;
      if (distM < roadLevel - 0.03) {
        return roadLevel - distM;
      }
      return 0;
    });

    const validHeights = heights.filter((h) => h > 0.01);

    if (validHeights.length < 10) {
      setVolumeData(null);
      return null;
    }

    const avgHeight = validHeights.reduce((a, b) => a + b, 0) / validHeights.length;
    const calibrationFactor = 60 / (avgHeight * 100);
    const calibratedHeight = avgHeight * calibrationFactor;
    const volume_m3 = vehicleParams.length_m * vehicleParams.width_m * calibratedHeight;
    const mass_tons = (volume_m3 * vehicleParams.coal_density_kg_m3) / 1000;
    const crossSectionArea = calibratedHeight * vehicleParams.width_m;

    const volume = {
      volume_m3: Math.round(volume_m3 * 100) / 100,
      cross_section_area: Math.round(crossSectionArea * 100) / 100,
      avg_height_m: Math.round(calibratedHeight * 100) / 100,
      coal_mass_tons: Math.round(mass_tons * 10) / 10,
    };

    setVolumeData(volume);
    return volume;
  };

  // ========== 3D СКАНИРОВАНИЕ ==========
  const generateScanId = () => `scan_${Date.now()}_${Math.random().toString(36).substr(2, 8)}`;

  const start3DScan = async () => {
    const scanId = generateScanId();
    setCurrentScanId(scanId);

    await scan3dApi.start(scanId, vehicleParams.length_m, vehicleParams.width_m);

    setIsScanning(true);
    setScanProfiles([]);
    setTotalVolume3d(null);
    setScanProgress(0);
    startTimeRef.current = Date.now();

    scanIntervalRef.current = window.setInterval(async () => {
      if (!isScanning) return;

      try {
        const response = await lidarApi.getScan();
        const data = response.data;

        if (data.distances_mm && data.distances_mm.length > 0) {
          const elapsedSeconds = (Date.now() - startTimeRef.current) / 1000;
          const assumedSpeed = 0.3;
          const position = elapsedSeconds * assumedSpeed;

          await scan3dApi.addProfile(scanId, data.distances_mm, position);

          const roadLevel = Math.max(...data.distances_mm) / 1000;
          const heights = data.distances_mm.map((d: number) => {
            const distM = d / 1000;
            if (distM < roadLevel - 0.03) return roadLevel - distM;
            return 0;
          });
          const validHeights = heights.filter((h: number) => h > 0.01);
          const avgHeight = validHeights.length
            ? validHeights.reduce((a: number, b: number) => a + b, 0) / validHeights.length
            : 0;
          const crossSection = avgHeight * vehicleParams.width_m;

          setScanProfiles((prev) => [
            ...prev,
            {
              timestamp: Date.now(),
              position_m: position,
              distances_mm: data.distances_mm,
              heights_m: [],
              cross_section_m2: crossSection,
            },
          ]);

          setScanProgress(Math.min(100, (position / vehicleParams.length_m) * 100));
        }
      } catch (err) {
        console.error("Scan error:", err);
      }
    }, 100);
  };

  const stop3DScan = async () => {
  if (scanIntervalRef.current) {
    clearInterval(scanIntervalRef.current);
    scanIntervalRef.current = undefined;
  }
  
  if (currentScanId) {
    try {
      const response = await scan3dApi.stop(currentScanId);
      const result = response.data;
      setTotalVolume3d(result.total_volume_m3);
      setSuccess(`3D сканирование завершено! Объём: ${result.total_volume_m3} м³, Масса: ${result.total_mass_tons} т`);
      
      // Сохраняем 3D результат в БД с правильными параметрами
      // Используем result.total_volume_m3 как объём
      const measureResponse = await lidarApi.measure({
        truck_length_m: vehicleParams.length_m,
        truck_width_m: vehicleParams.width_m,
        coal_density_kg_m3: vehicleParams.coal_density_kg_m3
      });
      
      console.log(" 3D результат сохранён в БД:", measureResponse.data);
      
      // Обновляем список измерений
      await fetchMeasurements();
      
    } catch (err) {
      console.error("Error stopping 3D scan:", err);
      setError("Ошибка при завершении 3D сканирования");
    }
  }
  
  setIsScanning(false);
};

  const reset3DScan = () => {
    setScanProfiles([]);
    setTotalVolume3d(null);
    setScanProgress(0);
  };

  // ========== ОДНОРАЗОВОЕ ИЗМЕРЕНИЕ ==========
  const performMeasurement = async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    
    try {
      const response = await lidarApi.measure({
        truck_length_m: vehicleParams.length_m,
        truck_width_m: vehicleParams.width_m,
        coal_density_kg_m3: vehicleParams.coal_density_kg_m3
      });
      
      setSuccess(`Измерение сохранено! Объём: ${response.data.volume_m3} м³, Масса: ${response.data.mass_tons} т`);
      
      setLidarData({
        timestamp: response.data.timestamp,
        points_count: response.data.points_count,
        distances_mm: response.data.distances_mm,
        distances_m: response.data.distances_mm.map((d: number) => d / 1000),
        statistics: {
          min_mm: Math.min(...response.data.distances_mm),
          max_mm: Math.max(...response.data.distances_mm),
          avg_mm: response.data.distances_mm.reduce((a: number, b: number) => a + b, 0) / response.data.distances_mm.length,
          min_m: Math.min(...response.data.distances_mm) / 1000,
          max_m: Math.max(...response.data.distances_mm) / 1000,
          avg_m: (response.data.distances_mm.reduce((a: number, b: number) => a + b, 0) / response.data.distances_mm.length) / 1000
        }
      });
      
      setVolumeData({
        volume_m3: response.data.volume_m3,
        cross_section_area: response.data.cross_section_m2,
        avg_height_m: response.data.avg_height_m,
        coal_mass_tons: response.data.mass_tons
      });
      
      checkEmptyStatus({
        points_count: response.data.points_count,
        distances_mm: response.data.distances_mm,
        distances_m: response.data.distances_mm.map((d: number) => d / 1000),
        timestamp: response.data.timestamp,
        statistics: {
          min_mm: Math.min(...response.data.distances_mm),
          max_mm: Math.max(...response.data.distances_mm),
          avg_mm: response.data.distances_mm.reduce((a: number, b: number) => a + b, 0) / response.data.distances_mm.length,
          min_m: Math.min(...response.data.distances_mm) / 1000,
          max_m: Math.max(...response.data.distances_mm) / 1000,
          avg_m: (response.data.distances_mm.reduce((a: number, b: number) => a + b, 0) / response.data.distances_mm.length) / 1000
        }
      }, {
        volume_m3: response.data.volume_m3,
        cross_section_area: response.data.cross_section_m2,
        avg_height_m: response.data.avg_height_m,
        coal_mass_tons: response.data.mass_tons
      });
      
      await fetchMeasurements();
      
      if (response.data.distances_mm && response.data.distances_mm.length > 0) {
        drawLidarData({
          distances_mm: response.data.distances_mm,
          distances_m: response.data.distances_mm.map((d: number) => d / 1000),
          points_count: response.data.points_count,
          timestamp: response.data.timestamp,
          statistics: {
            min_mm: Math.min(...response.data.distances_mm),
            max_mm: Math.max(...response.data.distances_mm),
            avg_mm: response.data.distances_mm.reduce((a: number, b: number) => a + b, 0) / response.data.distances_mm.length,
            min_m: Math.min(...response.data.distances_mm) / 1000,
            max_m: Math.max(...response.data.distances_mm) / 1000,
            avg_m: (response.data.distances_mm.reduce((a: number, b: number) => a + b, 0) / response.data.distances_mm.length) / 1000
          }
        });
        drawDistanceChart({
          distances_mm: response.data.distances_mm,
          distances_m: response.data.distances_mm.map((d: number) => d / 1000),
          points_count: response.data.points_count,
          timestamp: response.data.timestamp,
          statistics: {
            min_mm: Math.min(...response.data.distances_mm),
            max_mm: Math.max(...response.data.distances_mm),
            avg_mm: response.data.distances_mm.reduce((a: number, b: number) => a + b, 0) / response.data.distances_mm.length,
            min_m: Math.min(...response.data.distances_mm) / 1000,
            max_m: Math.max(...response.data.distances_mm) / 1000,
            avg_m: (response.data.distances_mm.reduce((a: number, b: number) => a + b, 0) / response.data.distances_mm.length) / 1000
          }
        });
      }
      
    } catch (err: any) {
      console.error("Error performing measurement:", err);
      setError(err.response?.data?.detail || "Ошибка при измерении");
    } finally {
      setSaving(false);
      setTimeout(() => setSuccess(null), 5000);
    }
  };

  const fetchLidarData = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await lidarApi.getScan();
      setLidarData(response.data);

      const calculatedVolume = calculateVolume(response.data);
      checkEmptyStatus(response.data, calculatedVolume);

      if (response.data.distances_mm && response.data.distances_mm.length > 0) {
        drawLidarData(response.data);
        drawDistanceChart(response.data);
      }
    } catch (err: any) {
      console.error("Error fetching lidar data:", err);
      setError(err.response?.data?.detail || "Ошибка получения данных с лидара");
    } finally {
      setLoading(false);
    }
  };

  // 3D визуализация (тепловая карта)
  const draw3DHeatmap = () => {
    const canvas = canvasRef.current;
    if (!canvas || scanProfiles.length === 0) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;

    ctx.fillStyle = "#1a1a1a";
    ctx.fillRect(0, 0, width, height);

    const allHeights = scanProfiles.map((p) => p.cross_section_m2 / vehicleParams.width_m);
    const maxHeight = Math.max(...allHeights, 0.5);

    const cellW = width / scanProfiles.length;
    const maxCellH = height * 0.7;

    for (let x = 0; x < scanProfiles.length; x++) {
      const profile = scanProfiles[x];
      const avgHeight = profile.cross_section_m2 / vehicleParams.width_m;
      const cellH = (avgHeight / maxHeight) * maxCellH;

      const ratio = Math.min(1, avgHeight / maxHeight);
      const r = Math.min(255, Math.floor(ratio * 255));
      const g = Math.min(255, Math.floor((1 - ratio) * 255));
      const b = 50;

      ctx.fillStyle = `rgb(${r}, ${g}, ${b})`;
      ctx.fillRect(x * cellW, height - cellH, cellW - 1, cellH);
    }

    ctx.fillStyle = "#ffffff";
    ctx.font = "10px Arial";
    ctx.fillText(`Длина кузова: ${vehicleParams.length_m}м`, 10, 20);
    ctx.fillText(`Профилей: ${scanProfiles.length}`, 10, 35);
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

    const startAngleDeg = -35;
    const stopAngleDeg = 35;

    const leftRad = (startAngleDeg * Math.PI) / 180;
    const leftX = centerX + Math.cos(leftRad) * maxRadius;
    const leftY = centerY + Math.sin(leftRad) * maxRadius;
    ctx.beginPath();
    ctx.moveTo(centerX, centerY);
    ctx.lineTo(leftX, leftY);
    ctx.strokeStyle = "#00ff00";
    ctx.lineWidth = 1;
    ctx.stroke();

    const rightRad = (stopAngleDeg * Math.PI) / 180;
    const rightX = centerX + Math.cos(rightRad) * maxRadius;
    const rightY = centerY + Math.sin(rightRad) * maxRadius;
    ctx.beginPath();
    ctx.moveTo(centerX, centerY);
    ctx.lineTo(rightX, rightY);
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(centerX, centerY, maxRadius * 0.8, leftRad, rightRad);
    ctx.strokeStyle = "#00ff00";
    ctx.setLineDash([5, 5]);
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.fillStyle = "#00ff00";
    ctx.font = "10px Arial";
    ctx.fillText(`-35°`, leftX - 15, leftY);
    ctx.fillText(`+35°`, rightX + 5, rightY - 5);
    ctx.fillText(`70° сектор`, centerX + 20, centerY - maxRadius * 0.75);

    for (let angle = -30; angle <= 30; angle += 10) {
      const rad = (angle * Math.PI) / 180;
      const x = centerX + Math.cos(rad) * (maxRadius - 10);
      const y = centerY + Math.sin(rad) * (maxRadius - 10);
      ctx.beginPath();
      ctx.moveTo(centerX, centerY);
      ctx.lineTo(x, y);
      ctx.strokeStyle = "#444444";
      ctx.stroke();

      if (angle !== 0) {
        ctx.fillStyle = "#666666";
        ctx.font = "9px Arial";
        ctx.fillText(`${angle}°`, x, y);
      }
    }

    const sectorAngleDeg = stopAngleDeg - startAngleDeg;
    const angleStepDeg = sectorAngleDeg / data.distances_mm.length;

    for (let i = 0; i < data.distances_mm.length; i++) {
      const distanceM = data.distances_mm[i] / 1000;
      if (distanceM === 0) continue;
      if (distanceM > maxDisplayDistance) continue;

      const currentAngleDeg = startAngleDeg + i * angleStepDeg;
      const currentAngleRad = (currentAngleDeg * Math.PI) / 180;
      const radius = (distanceM / maxDisplayDistance) * maxRadius;
      const x = centerX + Math.cos(currentAngleRad) * radius;
      const y = centerY + Math.sin(currentAngleRad) * radius;

      if (distanceM < 1) ctx.fillStyle = "#ff4444";
      else if (distanceM < 3) ctx.fillStyle = "#ffaa44";
      else ctx.fillStyle = "#44ff44";

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

    ctx.fillStyle = "#888888";
    ctx.font = "10px Arial";
    ctx.fillText("Сектор сканирования: 70° (от -35° до +35°)", centerX, height - 10);
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
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
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
      ctx.fillText("Уровень борта (3м)", width - 120, thresholdY - 2);
    }

    ctx.fillStyle = "#666666";
    ctx.font = "12px Arial";
    ctx.fillText("Длина кузова", width / 2 - 40, height - 5);

    ctx.save();
    ctx.translate(15, height / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText("Расстояние до лидара (м)", -20, 0);
    ctx.restore();
  };

  useEffect(() => {
  // Первоначальная загрузка
  fetchStatus();
  fetchCameraStatus();
  fetchLidarData();
  fetchCameraFrame();
  fetchMeasurements();
  
  // АВТООБНОВЛЕНИЕ (раз в 2 секунды)
  const autoRefreshInterval = setInterval(() => {
    fetchLidarData();
    if (showCamera) fetchCameraFrame();
  }, 2000);
  
  return () => {
    clearInterval(autoRefreshInterval);
  };
}, []);  // ← НЕТ зависимости от showCamera!

// Отдельный эффект для showCamera (чтобы перезапускать интервал при изменении)
useEffect(() => {
  // Этот эффект не нужен для автообновления, оставьте как есть
}, [showCamera]);

useEffect(() => {
  if (lidarData && lidarData.distances_mm) {
    drawLidarData(lidarData);
    drawDistanceChart(lidarData);
  }
}, [lidarData]);

useEffect(() => {
  if (scanProfiles.length > 0) {
    draw3DHeatmap();
  }
}, [scanProfiles]);

useEffect(() => {
  return () => {
    if (scanIntervalRef.current) {
      clearInterval(scanIntervalRef.current);
    }
  };
}, []);

  return (
    <div style={{ padding: "20px", backgroundColor: "#f5f5f5", borderRadius: "8px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px", flexWrap: "wrap", gap: "10px" }}>
        <h2 style={{ margin: 0 }}> Измерение объема угля в кузове</h2>
        <div style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "5px" }}>
            <input type="checkbox" checked={showCamera} onChange={(e) => setShowCamera(e.target.checked)} />
             Показывать камеру
          </label>
          <button
            onClick={fetchLidarData}
            disabled={loading}
            style={{ padding: "8px 16px", backgroundColor: "#6c757d", color: "white", border: "none", borderRadius: "4px", cursor: loading ? "not-allowed" : "pointer" }}
          >
            {loading ? "Загрузка..." : " Обновить"}
          </button>
          <button
            onClick={performMeasurement}
            disabled={saving}
            style={{ padding: "8px 16px", backgroundColor: "#28a745", color: "white", border: "none", borderRadius: "4px", cursor: saving ? "not-allowed" : "pointer" }}
          >
            {saving ? "Сохранение..." : " 2D Измерить"}
          </button>
          {!isScanning ? (
            <button
              onClick={start3DScan}
              style={{ padding: "8px 16px", backgroundColor: "#007bff", color: "white", border: "none", borderRadius: "4px", cursor: "pointer" }}
            >
               Начать 3D сканирование
            </button>
          ) : (
            <button
              onClick={stop3DScan}
              style={{ padding: "8px 16px", backgroundColor: "#dc3545", color: "white", border: "none", borderRadius: "4px", cursor: "pointer" }}
            >
              ⏹ Остановить 3D сканирование
            </button>
          )}
          <button
            onClick={() => setShowHistory(!showHistory)}
            style={{ padding: "8px 16px", backgroundColor: "#17a2b8", color: "white", border: "none", borderRadius: "4px", cursor: "pointer" }}
          >
            {showHistory ? " Скрыть историю" : " История измерений"}
          </button>
        </div>
      </div>

      {/* Статус подключения */}
      <div style={{ marginBottom: "20px", display: "flex", gap: "20px", flexWrap: "wrap" }}>
        <div style={{ padding: "10px", backgroundColor: "white", borderRadius: "4px", flex: 1 }}>
          <span> Лидар: </span>
          <span style={{ color: status?.connected ? "#28a745" : "#dc3545", fontWeight: "bold" }}>
            {status?.connected ? "✅ Подключен" : "❌ Не подключен"}
          </span>
          {status && <span style={{ marginLeft: "10px", fontSize: "12px" }}>{status.host}:{status.port}</span>}
        </div>
        <div style={{ padding: "10px", backgroundColor: "white", borderRadius: "4px", flex: 1 }}>
          <span> Камера: </span>
          <span style={{ color: cameraStatus?.connected ? "#28a745" : "#dc3545", fontWeight: "bold" }}>
            {cameraStatus?.connected ? "✅ Подключена" : "❌ Не подключена"}
          </span>
          {cameraStatus?.ip && <span style={{ marginLeft: "10px", fontSize: "12px" }}>{cameraStatus.ip}</span>}
        </div>
      </div>

      {error && <div style={{ marginBottom: "20px", padding: "10px", backgroundColor: "#f8d7da", color: "#721c24", borderRadius: "4px" }}>⚠️ {error}</div>}
      {success && <div style={{ marginBottom: "20px", padding: "10px", backgroundColor: "#d4edda", color: "#155724", borderRadius: "4px" }}>✅ {success}</div>}

      {/* 3D прогресс */}
      {isScanning && (
        <div style={{ marginBottom: "20px", padding: "15px", backgroundColor: "white", borderRadius: "12px" }}>
          <div style={{ marginBottom: "10px" }}>
            <div style={{ height: "10px", backgroundColor: "#e0e0e0", borderRadius: "5px", overflow: "hidden" }}>
              <div style={{ width: `${scanProgress}%`, height: "100%", backgroundColor: "#007bff", transition: "width 0.3s" }} />
            </div>
            <div style={{ fontSize: "12px", color: "#666", marginTop: "5px" }}>
              Прогресс: {Math.round(scanProgress)}% | Профилей: {scanProfiles.length}
            </div>
          </div>
          {totalVolume3d !== null && (
            <div style={{ background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)", padding: "15px", borderRadius: "8px", color: "white", textAlign: "center" }}>
              <div style={{ fontSize: "14px", opacity: 0.9 }}> 3D ОБЪЁМ (интегральный)</div>
              <div style={{ fontSize: "36px", fontWeight: "bold" }}>{totalVolume3d} м³</div>
              <div style={{ fontSize: "12px" }}>По {scanProfiles.length} профилям | Длина: {vehicleParams.length_m}м</div>
            </div>
          )}
          <canvas ref={canvasRef} width={600} height={200} style={{ width: "100%", height: "200px", border: "1px solid #ddd", borderRadius: "4px", backgroundColor: "#1a1a1a", marginTop: "10px" }} />
          <div style={{ fontSize: "11px", color: "#888", marginTop: "5px", textAlign: "center" }}>
            🔴 Красный - высокая насыпь | 🟢 Зелёный - низкая | Тепловая карта высот
          </div>
        </div>
      )}

      {/* Карточка статуса "Пусто/Не пусто" */}
      {emptyStatus && (
        <div style={{
          background: emptyStatus.is_empty ? "linear-gradient(135deg, #ff6b6b 0%, #c92a2a 100%)" : "linear-gradient(135deg, #51cf66 0%, #2f9e44 100%)",
          padding: "20px",
          borderRadius: "12px",
          color: "white",
          marginBottom: "20px",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
          gap: "15px",
        }}>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: "12px", opacity: 0.9 }}>{emptyStatus.is_empty ? " СТАТУС" : " СТАТУС"}</div>
            <div style={{ fontSize: "28px", fontWeight: "bold" }}>{emptyStatus.is_empty ? "КУЗОВ ПУСТ" : "КУЗОВ ЗАПОЛНЕН"}</div>
          </div>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: "12px", opacity: 0.9 }}>Уверенность</div>
            <div style={{ fontSize: "28px", fontWeight: "bold" }}>{emptyStatus.confidence}%</div>
            <div style={{ fontSize: "11px", opacity: 0.8 }}>{emptyStatus.reason}</div>
          </div>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: "12px", opacity: 0.9 }}>Точек сканирования</div>
            <div style={{ fontSize: "28px", fontWeight: "bold" }}>{emptyStatus.points_count}</div>
          </div>
        </div>
      )}

      {/* Карточка с 2D объемом угля */}
      {volumeData && !emptyStatus?.is_empty && (
        <div style={{
          background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
          padding: "20px",
          borderRadius: "12px",
          color: "white",
          marginBottom: "20px",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
          gap: "15px",
        }}>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: "12px", opacity: 0.9 }}>2D Объем угля</div>
            <div style={{ fontSize: "32px", fontWeight: "bold" }}>{volumeData.volume_m3} м³</div>
            <div style={{ fontSize: "11px", opacity: 0.7 }}>(один профиль)</div>
          </div>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: "12px", opacity: 0.9 }}>Масса угля</div>
            <div style={{ fontSize: "32px", fontWeight: "bold" }}>{volumeData.coal_mass_tons} т</div>
          </div>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: "12px", opacity: 0.9 }}>Сечение угля</div>
            <div style={{ fontSize: "24px", fontWeight: "bold" }}>{volumeData.cross_section_area} м²</div>
          </div>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: "12px", opacity: 0.9 }}>Ср. высота</div>
            <div style={{ fontSize: "24px", fontWeight: "bold" }}>{volumeData.avg_height_m} м</div>
          </div>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: showCamera ? "1fr 1fr" : "1fr", gap: "20px" }}>
        {/* Левая колонка - Лидар */}
        <div>
          <div style={{ backgroundColor: "white", borderRadius: "8px", padding: "10px", marginBottom: "20px" }}>
            <h3 style={{ marginTop: 0, marginBottom: "15px" }}> Сканирование кузова автомобиля</h3>
            <canvas ref={canvasRef} width={500} height={500} style={{ width: "100%", maxWidth: "500px", height: "auto", border: "1px solid #ddd", borderRadius: "4px", display: "block", margin: "0 auto" }} />
            <div style={{ fontSize: "12px", color: "#666", marginTop: "10px", textAlign: "center" }}>
              🟢 Нормально (&gt;3м) &nbsp;&nbsp; 🟡 Внимание (1-3м) &nbsp;&nbsp; 🔴 Опасно (&lt;1м)
            </div>
          </div>

          {/* Статистика лидара */}
          {lidarData && lidarData.points_count > 0 && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "10px", marginBottom: "20px" }}>
              <div style={{ padding: "10px", backgroundColor: "white", borderRadius: "4px", textAlign: "center" }}>
                <div style={{ fontSize: "11px", color: "#666" }}>Точек</div>
                <div style={{ fontSize: "20px", fontWeight: "bold" }}>{lidarData.points_count}</div>
              </div>
              <div style={{ padding: "10px", backgroundColor: "white", borderRadius: "4px", textAlign: "center" }}>
                <div style={{ fontSize: "11px", color: "#666" }}>Мин. расстояние</div>
                <div style={{ fontSize: "20px", fontWeight: "bold" }}>{lidarData.statistics.min_m}м</div>
              </div>
              <div style={{ padding: "10px", backgroundColor: "white", borderRadius: "4px", textAlign: "center" }}>
                <div style={{ fontSize: "11px", color: "#666" }}>Макс. расстояние</div>
                <div style={{ fontSize: "20px", fontWeight: "bold" }}>{lidarData.statistics.max_m}м</div>
              </div>
            </div>
          )}

          {/* График профиля */}
          {lidarData && lidarData.distances_m && lidarData.distances_m.length > 0 && (
            <div style={{ padding: "15px", backgroundColor: "white", borderRadius: "4px" }}>
              <h3 style={{ marginTop: 0, marginBottom: "15px" }}> Профиль угля в кузове</h3>
              <canvas ref={chartCanvasRef} width={600} height={200} style={{ width: "100%", height: "200px", border: "1px solid #ddd", borderRadius: "4px" }} />
              <div style={{ fontSize: "12px", color: "#666", marginTop: "10px" }}>🔴 Красная линия - уровень борта кузова (3 метра от лидара)</div>
              <div style={{ fontSize: "11px", color: "#888", marginTop: "5px" }}>📌 Выше красной линии - есть уголь, ниже - пустое место</div>
            </div>
          )}
        </div>

        {/* Правая колонка - Камера */}
        {showCamera && (
          <div>
            <div style={{ backgroundColor: "white", borderRadius: "8px", padding: "10px" }}>
              <h3 style={{ marginTop: 0, marginBottom: "15px" }}> Контроль качества</h3>
              {cameraLoading && <div style={{ textAlign: "center", padding: "20px" }}>Загрузка кадра...</div>}
              {cameraImage && !cameraLoading && <img src={cameraImage} alt="Camera feed" style={{ width: "100%", borderRadius: "4px", border: "1px solid #ddd" }} />}
              {!cameraImage && !cameraLoading && (
                <div style={{ textAlign: "center", padding: "40px", color: "#666", background: "#f9f9f9", borderRadius: "4px" }}>
                   Нет изображения с камеры<br />
                  <span style={{ fontSize: "12px" }}>Проверьте подключение камеры</span>
                </div>
              )}
              <div style={{ fontSize: "12px", color: "#666", marginTop: "10px", textAlign: "center" }}>
                {cameraStatus?.connected ? "Камера работает" : "Ожидание подключения камеры"}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Время последнего обновления */}
      {lidarData && (
        <div style={{ marginTop: "15px", fontSize: "12px", color: "#666", textAlign: "center" }}>
          Последнее обновление: {new Date(lidarData.timestamp).toLocaleTimeString()}
        </div>
      )}

      {/* История измерений */}
      {showHistory && (
        <div style={{ marginTop: "20px", padding: "15px", backgroundColor: "white", borderRadius: "12px" }}>
          <h3 style={{ marginTop: 0, marginBottom: "15px" }}>📋 История измерений</h3>
          {measurements.length === 0 ? (
            <div style={{ textAlign: "center", padding: "20px", color: "#666" }}>Нет сохранённых измерений</div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ backgroundColor: "#f0f0f0" }}>
                    <th style={{ padding: "10px", border: "1px solid #ddd", textAlign: "left" }}>ID</th>
                    <th style={{ padding: "10px", border: "1px solid #ddd", textAlign: "left" }}>Дата/время</th>
                    <th style={{ padding: "10px", border: "1px solid #ddd", textAlign: "left" }}>Объём (м³)</th>
                    <th style={{ padding: "10px", border: "1px solid #ddd", textAlign: "left" }}>Масса (т)</th>
                    <th style={{ padding: "10px", border: "1px solid #ddd", textAlign: "left" }}>Высота (м)</th>
                    <th style={{ padding: "10px", border: "1px solid #ddd", textAlign: "left" }}>Статус</th>
                  </tr>
                </thead>
                <tbody>
                  {measurements.map((m) => (
                    <tr key={m.id}>
                      <td style={{ padding: "10px", border: "1px solid #ddd" }}>{m.id}</td>
                      <td style={{ padding: "10px", border: "1px solid #ddd" }}>{new Date(m.timestamp).toLocaleString()}</td>
                      <td style={{ padding: "10px", border: "1px solid #ddd" }}>{m.volume_m3}</td>
                      <td style={{ padding: "10px", border: "1px solid #ddd" }}>{m.mass_tons}</td>
                      <td style={{ padding: "10px", border: "1px solid #ddd" }}>{m.avg_height_m}</td>
                      <td style={{ padding: "10px", border: "1px solid #ddd", color: m.is_empty ? "#dc3545" : "#28a745" }}>
                        {m.is_empty ? "ПУСТ" : "ЗАПОЛНЕН"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Настройки автомобиля */}
      <details style={{ marginTop: "20px" }}>
        <summary style={{ cursor: "pointer", color: "#666", fontSize: "12px" }}>⚙️ Настройки автомобиля</summary>
        <div style={{ marginTop: "10px", padding: "15px", backgroundColor: "white", borderRadius: "4px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "15px" }}>
            <div>
              <label style={{ fontSize: "12px", color: "#666" }}> Длина кузова (м)</label>
              <input type="number" step="0.5" value={vehicleParams.length_m} onChange={(e) => setVehicleParams({ ...vehicleParams, length_m: parseFloat(e.target.value) })} style={{ width: "100%", padding: "5px", marginTop: "5px" }} />
            </div>
            <div>
              <label style={{ fontSize: "12px", color: "#666" }}> Ширина кузова (м)</label>
              <input type="number" step="0.1" value={vehicleParams.width_m} onChange={(e) => setVehicleParams({ ...vehicleParams, width_m: parseFloat(e.target.value) })} style={{ width: "100%", padding: "5px", marginTop: "5px" }} />
            </div>
            <div>
              <label style={{ fontSize: "12px", color: "#666" }}> Плотность угля (кг/м³)</label>
              <input type="number" step="10" value={vehicleParams.coal_density_kg_m3} onChange={(e) => setVehicleParams({ ...vehicleParams, coal_density_kg_m3: parseFloat(e.target.value) })} style={{ width: "100%", padding: "5px", marginTop: "5px" }} />
            </div>
          </div>
          <div style={{ marginTop: "10px", fontSize: "12px", color: "#888" }}>💡 Укажите реальные размеры кузова для точного расчёта</div>
        </div>
      </details>
    </div>
  );
};

export default LidarViewer;
