// // frontend/src/components/LidarViewer.tsx

// import React, { useState, useEffect, useRef } from "react";
// import { lidarApi, scan3dApi } from "../../services/api";
// import axios from "axios";

// // ⭐ ИНТЕРФЕЙС ДЛЯ BOX_INFO
// interface BoxInfo {
//   box_type: string; // "small" | "medium" | "large" | "unknown" | "none"
//   box_label: string; // "S" | "M" | "L" | "?" | "-"
//   box_name: string; // "Малая" | "Средняя" | "Большая"
//   emoji?: string;
//   size_mm: {
//     width: number;
//     depth: number;
//     height: number;
//   };
//   size_cm: {
//     width: number;
//     depth: number;
//     height: number;
//   };
//   detected: boolean;
//   confidence: number;
//   profile_name?: string;
//   vehicle_type?: string;
//   brand?: string;
//   model?: string;
//   profile_confidence?: number;
// }

// // ⭐ НОВЫЙ ИНТЕРФЕЙС ДЛЯ ОБЪЕМА
// interface VolumeInfo {
//   volume_m3: number;
//   avg_height_m: number;
//   cross_section_m2: number;
//   fill_percent: number;
// }

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
//   object_status?: string;
//   status_text?: string;
//   object_detected?: boolean;
//   is_empty?: boolean;
//   empty_confidence?: number;
//   object_type?: string;
//   object_height_mm?: number;
//   floor_level_mm?: number;
//   spread_mm?: number;
//   box_info?: BoxInfo;
//   volume_info?: VolumeInfo; // ⭐ НОВОЕ ПОЛЕ
//   profile?: any;
//   profile_confidence?: number;
//   reason?: string;
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

// interface ScanProfile {
//   timestamp: number;
//   position_m: number;
//   distances_mm: number[];
//   heights_m: number[];
//   cross_section_m2: number;
// }

// interface SavedMeasurement {
//   id: number;
//   timestamp: string;
//   points_count: number;
//   volume_m3: number;
//   mass_tons: number;
//   avg_height_m: number;
//   cross_section_m2: number;
//   is_empty: boolean;
// }

// const LidarViewer: React.FC = () => {
//   const [lidarData, setLidarData] = useState<LidarData | null>(null);
//   const [status, setStatus] = useState<{
//     connected: boolean;
//     host: string;
//     port: number;
//   } | null>(null);
//   const [cameraStatus, setCameraStatus] = useState<CameraStatus | null>(null);
//   const [cameraImage, setCameraImage] = useState<string | null>(null);
//   const [volumeData, setVolumeData] = useState<VolumeData | null>(null);
//   const [loading, setLoading] = useState(false);
//   const [saving, setSaving] = useState(false);
//   const [cameraLoading, setCameraLoading] = useState(false);
//   const [error, setError] = useState<string | null>(null);
//   const [success, setSuccess] = useState<string | null>(null);
//   const [showCamera, setShowCamera] = useState(false);
//   const [measurements, setMeasurements] = useState<SavedMeasurement[]>([]);
//   const [showHistory, setShowHistory] = useState(false);
//   const canvasRef = useRef<HTMLCanvasElement>(null);
//   const chartCanvasRef = useRef<HTMLCanvasElement>(null);

//   const [objectStatus, setObjectStatus] = useState<string>("unknown");
//   const [statusText, setStatusText] = useState<string>("⏳ Ожидание данных...");
//   const [statusColor, setStatusColor] = useState<string>("#2196F3");
//   const [showObjectMessage, setShowObjectMessage] = useState<boolean>(false);
//   const [emptyStatus, setEmptyStatus] = useState<{
//     is_empty: boolean;
//     confidence: number;
//     reason: string;
//     points_count: number;
//     object_status?: string;
//     status_description?: string;
//   } | null>(null);

//   // 3D сканирование
//   const [isScanning, setIsScanning] = useState(false);
//   const [scanProfiles, setScanProfiles] = useState<ScanProfile[]>([]);
//   const [totalVolume3d, setTotalVolume3d] = useState<number | null>(null);
//   const [scanProgress, setScanProgress] = useState(0);
//   const scanIntervalRef = useRef<number | undefined>(undefined);
//   const startTimeRef = useRef<number>(0);
//   const [currentScanId, setCurrentScanId] = useState<string | null>(null);
//   const isScanningRef = useRef(false);

//   const [vehicleParams, setVehicleParams] = useState({
//     length_m: 6.0,
//     width_m: 2.5,
//     coal_density_kg_m3: 850,
//   });

//   // ⭐ ФУНКЦИИ ДЛЯ ОТОБРАЖЕНИЯ
//   const getBoxColor = (boxType: string): string => {
//     switch (boxType) {
//       case "small":
//         return "#4CAF50";
//       case "medium":
//         return "#FF9800";
//       case "large":
//         return "#F44336";
//       case "none":
//         return "#9E9E9E";
//       default:
//         return "#9E9E9E";
//     }
//   };

//   const getBoxLabel = (boxType: string): string => {
//     switch (boxType) {
//       case "small":
//         return "S";
//       case "medium":
//         return "M";
//       case "large":
//         return "L";
//       default:
//         return "?";
//     }
//   };

//   const getStatusEmoji = (objectStatus: string, boxInfo?: BoxInfo): string => {
//     if (objectStatus === "no_object" || objectStatus === "no_data") return "📭";
//     if (boxInfo?.detected && boxInfo.vehicle_type === "box") {
//       return boxInfo.emoji || "📦";
//     }
//     if (objectStatus === "filled") return "📦✅";
//     if (objectStatus === "empty") return "📦";
//     return "📡";
//   };

//   const fetchStatus = async () => {
//     try {
//       const response = await lidarApi.getStatus();
//       setStatus(response.data);
//     } catch (err) {
//       console.error("Error fetching lidar status:", err);
//     }
//   };

//   const fetchCameraStatus = async () => {
//     try {
//       const response = await axios.get(
//         "http://localhost:8000/api/camera/status",
//       );
//       setCameraStatus(response.data);
//     } catch (err) {
//       console.error("Error fetching camera status:", err);
//     }
//   };

//   const fetchCameraFrame = async () => {
//     if (!showCamera) return;
//     setCameraLoading(true);
//     try {
//       const response = await axios.get(
//         "http://localhost:8000/api/camera/frame",
//         {
//           responseType: "blob",
//           timeout: 3000,
//         },
//       );
//       const imageUrl = URL.createObjectURL(response.data);
//       setCameraImage(imageUrl);
//     } catch (err) {
//       console.error("Error fetching camera frame:", err);
//     } finally {
//       setCameraLoading(false);
//     }
//   };

//   const fetchMeasurements = async () => {
//     try {
//       const response = await lidarApi.getMeasurements(20);
//       setMeasurements(response.data);
//     } catch (err) {
//       console.error("Error fetching measurements:", err);
//     }
//   };

//   const calculateCrossSection = (
//     distances_mm: number[],
//     roadLevel: number,
//     width_m: number,
//   ): number => {
//     if (!distances_mm.length) return 0;
//     const heights = distances_mm.map((d) => {
//       const distM = d / 1000;
//       if (distM < roadLevel - 0.03) return roadLevel - distM;
//       return 0;
//     });
//     const validHeights = heights.filter((h) => h > 0.01);
//     if (validHeights.length === 0) return 0;
//     const avgHeight =
//       validHeights.reduce((a, b) => a + b, 0) / validHeights.length;
//     return avgHeight * width_m;
//   };

//   const calculateVolume = (data: LidarData) => {
//     if (!data.distances_mm || data.distances_mm.length < 15) {
//       setVolumeData(null);
//       return null;
//     }

//     const roadLevel = Math.max(...data.distances_mm) / 1000;
//     const heights = data.distances_mm.map((d) => {
//       const distM = d / 1000;
//       if (distM < roadLevel - 0.03) {
//         return roadLevel - distM;
//       }
//       return 0;
//     });

//     const validHeights = heights.filter((h) => h > 0.01);

//     if (validHeights.length < 10) {
//       setVolumeData(null);
//       return null;
//     }

//     const avgHeight =
//       validHeights.reduce((a, b) => a + b, 0) / validHeights.length;
//     const calibrationFactor = 60 / (avgHeight * 100);
//     const calibratedHeight = avgHeight * calibrationFactor;
//     const volume_m3 =
//       vehicleParams.length_m * vehicleParams.width_m * calibratedHeight;
//     const mass_tons = (volume_m3 * vehicleParams.coal_density_kg_m3) / 1000;
//     const crossSectionArea = calibratedHeight * vehicleParams.width_m;

//     const volume = {
//       volume_m3: Math.round(volume_m3 * 100) / 100,
//       cross_section_area: Math.round(crossSectionArea * 100) / 100,
//       avg_height_m: Math.round(calibratedHeight * 100) / 100,
//       coal_mass_tons: Math.round(mass_tons * 10) / 10,
//     };

//     setVolumeData(volume);
//     return volume;
//   };

//   // ========== 3D СКАНИРОВАНИЕ ==========
//   const start3DScan = async () => {
//     console.log("🚀 1. start3DScan вызван");

//     try {
//       const response = await scan3dApi.start(
//         vehicleParams.length_m,
//         vehicleParams.width_m,
//       );
//       const scanId = response.data.scan_id;

//       console.log("✅ 2. Сессия создана на бэкенде, scanId:", scanId);

//       setCurrentScanId(scanId);
//       setIsScanning(true);
//       isScanningRef.current = true;
//       setScanProfiles([]);
//       setTotalVolume3d(null);
//       setScanProgress(0);
//       startTimeRef.current = Date.now();

//       if (scanIntervalRef.current) {
//         clearInterval(scanIntervalRef.current);
//       }

//       scanIntervalRef.current = window.setInterval(async () => {
//         if (!isScanningRef.current) {
//           console.log("⏸️ Сканирование остановлено");
//           return;
//         }

//         try {
//           const scanResponse = await lidarApi.getScan();
//           const data = scanResponse.data;

//           if (data.distances_mm && data.distances_mm.length > 0) {
//             const elapsedSeconds = (Date.now() - startTimeRef.current) / 1000;
//             const assumedSpeed = 0.3;
//             const position = elapsedSeconds * assumedSpeed;

//             await scan3dApi.addProfile(scanId, data.distances_mm, position);

//             const roadLevel = Math.max(...data.distances_mm) / 1000;
//             const heights = data.distances_mm.map((d: number) => {
//               const distM = d / 1000;
//               if (distM < roadLevel - 0.03) return roadLevel - distM;
//               return 0;
//             });
//             const validHeights = heights.filter((h: number) => h > 0.01);
//             const avgHeight = validHeights.length
//               ? validHeights.reduce((a: number, b: number) => a + b, 0) /
//                 validHeights.length
//               : 0;
//             const crossSection = avgHeight * vehicleParams.width_m;

//             setScanProfiles((prev) => [
//               ...prev,
//               {
//                 timestamp: Date.now(),
//                 position_m: position,
//                 distances_mm: data.distances_mm,
//                 heights_m: [],
//                 cross_section_m2: crossSection,
//               },
//             ]);

//             setScanProgress(
//               Math.min(100, (position / vehicleParams.length_m) * 100),
//             );
//           }
//         } catch (err) {
//           console.error("❌ Ошибка в интервале:", err);
//         }
//       }, 100);
//     } catch (error) {
//       console.error("❌ Ошибка при старте сканирования:", error);
//       setError("Не удалось начать 3D сканирование");
//     }
//   };

//   const stop3DScan = async () => {
//     console.log("⏹️ Остановка 3D сканирования, ID:", currentScanId);

//     isScanningRef.current = false;
//     setIsScanning(false);

//     if (scanIntervalRef.current) {
//       clearInterval(scanIntervalRef.current);
//       scanIntervalRef.current = undefined;
//     }

//     if (currentScanId) {
//       try {
//         const response = await scan3dApi.stop(currentScanId);
//         const result = response.data;
//         console.log("📦 Результат 3D:", result);

//         setTotalVolume3d(result.total_volume_m3);
//         setSuccess(
//           `3D сканирование завершено! Объём: ${result.total_volume_m3} м³, Масса: ${result.total_mass_tons} т`,
//         );

//         await fetchMeasurements();
//         console.log("📋 История обновлена");
//       } catch (err: any) {
//         console.error("Error stopping 3D scan:", err);
//         setError(
//           err.response?.data?.detail || "Ошибка при завершении 3D сканирования",
//         );
//       }
//     } else {
//       console.warn("Нет active scanId для остановки");
//     }
//   };

//   const reset3DScan = () => {
//     setScanProfiles([]);
//     setTotalVolume3d(null);
//     setScanProgress(0);
//   };

//   // ========== ОДНОРАЗОВОЕ ИЗМЕРЕНИЕ ==========
//   const performMeasurement = async () => {
//     setSaving(true);
//     setError(null);
//     setSuccess(null);

//     try {
//       const response = await lidarApi.measure({
//         truck_length_m: vehicleParams.length_m,
//         truck_width_m: vehicleParams.width_m,
//         coal_density_kg_m3: vehicleParams.coal_density_kg_m3,
//       });

//       setSuccess(
//         `Измерение сохранено! Объём: ${response.data.volume_m3} м³, Масса: ${response.data.mass_tons} т`,
//       );

//       setLidarData({
//         timestamp: response.data.timestamp,
//         points_count: response.data.points_count,
//         distances_mm: response.data.distances_mm,
//         distances_m: response.data.distances_mm.map((d: number) => d / 1000),
//         statistics: {
//           min_mm: Math.min(...response.data.distances_mm),
//           max_mm: Math.max(...response.data.distances_mm),
//           avg_mm:
//             response.data.distances_mm.reduce(
//               (a: number, b: number) => a + b,
//               0,
//             ) / response.data.distances_mm.length,
//           min_m: Math.min(...response.data.distances_mm) / 1000,
//           max_m: Math.max(...response.data.distances_mm) / 1000,
//           avg_m:
//             response.data.distances_mm.reduce(
//               (a: number, b: number) => a + b,
//               0,
//             ) /
//             response.data.distances_mm.length /
//             1000,
//         },
//         box_info: response.data.box_info,
//         volume_info: response.data.volume_info,
//       });

//       setVolumeData({
//         volume_m3: response.data.volume_m3,
//         cross_section_area: response.data.cross_section_m2,
//         avg_height_m: response.data.avg_height_m,
//         coal_mass_tons: response.data.mass_tons,
//       });

//       await fetchMeasurements();

//       if (response.data.distances_mm && response.data.distances_mm.length > 0) {
//         drawLidarData({
//           distances_mm: response.data.distances_mm,
//           distances_m: response.data.distances_mm.map((d: number) => d / 1000),
//           points_count: response.data.points_count,
//           timestamp: response.data.timestamp,
//           statistics: {
//             min_mm: Math.min(...response.data.distances_mm),
//             max_mm: Math.max(...response.data.distances_mm),
//             avg_mm:
//               response.data.distances_mm.reduce(
//                 (a: number, b: number) => a + b,
//                 0,
//               ) / response.data.distances_mm.length,
//             min_m: Math.min(...response.data.distances_mm) / 1000,
//             max_m: Math.max(...response.data.distances_mm) / 1000,
//             avg_m:
//               response.data.distances_mm.reduce(
//                 (a: number, b: number) => a + b,
//                 0,
//               ) /
//               response.data.distances_mm.length /
//               1000,
//           },
//           box_info: response.data.box_info,
//           volume_info: response.data.volume_info,
//         });
//         drawDistanceChart({
//           distances_mm: response.data.distances_mm,
//           distances_m: response.data.distances_mm.map((d: number) => d / 1000),
//           points_count: response.data.points_count,
//           timestamp: response.data.timestamp,
//           statistics: {
//             min_mm: Math.min(...response.data.distances_mm),
//             max_mm: Math.max(...response.data.distances_mm),
//             avg_mm:
//               response.data.distances_mm.reduce(
//                 (a: number, b: number) => a + b,
//                 0,
//               ) / response.data.distances_mm.length,
//             min_m: Math.min(...response.data.distances_mm) / 1000,
//             max_m: Math.max(...response.data.distances_mm) / 1000,
//             avg_m:
//               response.data.distances_mm.reduce(
//                 (a: number, b: number) => a + b,
//                 0,
//               ) /
//               response.data.distances_mm.length /
//               1000,
//           },
//         });
//       }
//     } catch (err: any) {
//       console.error("Error performing measurement:", err);
//       setError(err.response?.data?.detail || "Ошибка при измерении");
//     } finally {
//       setSaving(false);
//       setTimeout(() => setSuccess(null), 5000);
//     }
//   };

//   const fetchLidarData = async () => {
//     setLoading(true);
//     setError(null);
//     try {
//       const response = await lidarApi.getScan();
//       const data = response.data;
//       console.log("📦 Данные с бэкенда:", data);
//       console.log("📦 box_info:", data.box_info);

//       setLidarData(data);

//       const objectStatus = data.object_status || "unknown";
//       const statusText = data.status_text || "Неизвестно";
//       const isEmpty = data.is_empty !== undefined ? data.is_empty : true;

//       setObjectStatus(objectStatus);
//       setStatusText(statusText);

//       if (objectStatus === "no_object" || objectStatus === "no_data") {
//         setShowObjectMessage(true);
//         setStatusColor("#888888");
//         const canvas = canvasRef.current;
//         if (canvas) {
//           const ctx = canvas.getContext("2d");
//           if (ctx) {
//             ctx.fillStyle = "#1a1a1a";
//             ctx.fillRect(0, 0, canvas.width, canvas.height);
//           }
//         }
//       } else {
//         setShowObjectMessage(false);
//         if (objectStatus === "empty" || isEmpty) {
//           setStatusColor("#FF9800");
//         } else if (objectStatus === "filled") {
//           setStatusColor("#4CAF50");
//         } else {
//           setStatusColor("#2196F3");
//         }
//       }

//       setEmptyStatus({
//         is_empty: isEmpty,
//         confidence: data.empty_confidence || 80,
//         reason: data.reason || statusText || "Статус от бэкенда",
//         points_count: data.points_count || 0,
//         object_status: objectStatus,
//         status_description: statusText,
//       });

//       const calculatedVolume = calculateVolume(data);
//       if (calculatedVolume) {
//         setVolumeData(calculatedVolume);
//       }

//       if (
//         data.distances_mm &&
//         data.distances_mm.length > 0 &&
//         objectStatus !== "no_object"
//       ) {
//         drawLidarData(data);
//         drawDistanceChart(data);
//       }
//     } catch (err: any) {
//       console.error("Error fetching lidar data:", err);
//       setError(
//         err.response?.data?.detail || "Ошибка получения данных с лидара",
//       );
//     } finally {
//       setLoading(false);
//     }
//   };

//   const draw3DHeatmap = () => {
//     const canvas = canvasRef.current;
//     if (!canvas || scanProfiles.length === 0) return;

//     const ctx = canvas.getContext("2d");
//     if (!ctx) return;

//     const width = canvas.width;
//     const height = canvas.height;

//     ctx.fillStyle = "#1a1a1a";
//     ctx.fillRect(0, 0, width, height);

//     const allHeights = scanProfiles.map(
//       (p) => p.cross_section_m2 / vehicleParams.width_m,
//     );
//     const maxHeight = Math.max(...allHeights, 0.5);

//     const cellW = width / scanProfiles.length;
//     const maxCellH = height * 0.7;

//     for (let x = 0; x < scanProfiles.length; x++) {
//       const profile = scanProfiles[x];
//       const avgHeight = profile.cross_section_m2 / vehicleParams.width_m;
//       const cellH = (avgHeight / maxHeight) * maxCellH;

//       const ratio = Math.min(1, avgHeight / maxHeight);
//       const r = Math.min(255, Math.floor(ratio * 255));
//       const g = Math.min(255, Math.floor((1 - ratio) * 255));
//       const b = 50;

//       ctx.fillStyle = `rgb(${r}, ${g}, ${b})`;
//       ctx.fillRect(x * cellW, height - cellH, cellW - 1, cellH);
//     }

//     ctx.fillStyle = "#ffffff";
//     ctx.font = "10px Arial";
//     ctx.fillText(`Длина кузова: ${vehicleParams.length_m}м`, 10, 20);
//     ctx.fillText(`Профилей: ${scanProfiles.length}`, 10, 35);
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

//     const sectorAngleDeg = totalAngleDeg;
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
//     ctx.fillText(
//       "Сектор сканирования: 70° (от -35° до +35°)",
//       centerX,
//       height - 10,
//     );
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
//     fetchMeasurements();

//     const autoRefreshInterval = setInterval(() => {
//       fetchLidarData();
//       if (showCamera) fetchCameraFrame();
//     }, 2000);

//     return () => {
//       clearInterval(autoRefreshInterval);
//     };
//   }, []);

//   useEffect(() => {
//     if (lidarData && lidarData.distances_mm) {
//       drawLidarData(lidarData);
//       drawDistanceChart(lidarData);
//     }
//   }, [lidarData]);

//   useEffect(() => {
//     if (scanProfiles.length > 0) {
//       draw3DHeatmap();
//     }
//   }, [scanProfiles]);

//   useEffect(() => {
//     return () => {
//       if (scanIntervalRef.current) {
//         clearInterval(scanIntervalRef.current);
//       }
//     };
//   }, []);

//   const getStatusIcon = () => {
//     switch (objectStatus) {
//       case "no_object":
//         return "📭";
//       case "no_data":
//         return "❌";
//       case "empty":
//         return "📦";
//       case "filled":
//         return "📦✅";
//       case "unknown":
//         return "⏳";
//       default:
//         return "📡";
//     }
//   };

//   return (
//     <div
//       style={{
//         padding: "20px",
//         backgroundColor: "#f5f5f5",
//         borderRadius: "8px",
//       }}
//     >
//       <div
//         style={{
//           display: "flex",
//           justifyContent: "space-between",
//           alignItems: "center",
//           marginBottom: "20px",
//           flexWrap: "wrap",
//           gap: "10px",
//         }}
//       >
//         <h2 style={{ margin: 0, fontSize: "22px" }}>📊 Уголь-Контроль</h2>
//         <div
//           style={{
//             display: "flex",
//             gap: "8px",
//             alignItems: "center",
//             flexWrap: "wrap",
//           }}
//         >
//           <label
//             style={{
//               display: "flex",
//               alignItems: "center",
//               gap: "4px",
//               fontSize: "13px",
//             }}
//           >
//             <input
//               type="checkbox"
//               checked={showCamera}
//               onChange={(e) => setShowCamera(e.target.checked)}
//             />
//             📷
//           </label>
//           <button
//             onClick={fetchLidarData}
//             disabled={loading}
//             style={{
//               padding: "6px 14px",
//               backgroundColor: "#6c757d",
//               color: "white",
//               border: "none",
//               borderRadius: "4px",
//               cursor: loading ? "not-allowed" : "pointer",
//               fontSize: "13px",
//             }}
//           >
//             {loading ? "..." : "🔄"}
//           </button>
//           <button
//             onClick={performMeasurement}
//             disabled={saving}
//             style={{
//               padding: "6px 14px",
//               backgroundColor: "#28a745",
//               color: "white",
//               border: "none",
//               borderRadius: "4px",
//               cursor: saving ? "not-allowed" : "pointer",
//               fontSize: "13px",
//             }}
//           >
//             {saving ? "..." : "📐"}
//           </button>
//           {!isScanning ? (
//             <button
//               onClick={start3DScan}
//               style={{
//                 padding: "6px 14px",
//                 backgroundColor: "#007bff",
//                 color: "white",
//                 border: "none",
//                 borderRadius: "4px",
//                 cursor: "pointer",
//                 fontSize: "13px",
//               }}
//             >
//               🚀3D
//             </button>
//           ) : (
//             <button
//               onClick={stop3DScan}
//               style={{
//                 padding: "6px 14px",
//                 backgroundColor: "#dc3545",
//                 color: "white",
//                 border: "none",
//                 borderRadius: "4px",
//                 cursor: "pointer",
//                 fontSize: "13px",
//               }}
//             >
//               ⏹
//             </button>
//           )}
//           <button
//             onClick={() => setShowHistory(!showHistory)}
//             style={{
//               padding: "6px 14px",
//               backgroundColor: "#17a2b8",
//               color: "white",
//               border: "none",
//               borderRadius: "4px",
//               cursor: "pointer",
//               fontSize: "13px",
//             }}
//           >
//             {showHistory ? "📕" : "📋"}
//           </button>
//         </div>
//       </div>

//       {/* ═══════════════════════════════════════════════════════════ */}
//       {/* ⭐ ЕДИНЫЙ БОЛЬШОЙ БЛОК - ВСЯ ИНФОРМАЦИЯ В ОДНОМ МЕСТЕ */}
//       {/* ═══════════════════════════════════════════════════════════ */}
//       {statusText && (
//         <div
//           style={{
//             padding: "16px 20px",
//             borderRadius: "10px",
//             backgroundColor: statusColor + "15",
//             border: `2px solid ${statusColor}`,
//             color: statusColor,
//             marginBottom: "16px",
//             fontSize: "15px",
//           }}
//         >
//           {/* Ряд 1: Статус + Тип + Размеры + Подключения */}
//           <div
//             style={{
//               display: "flex",
//               alignItems: "center",
//               gap: "12px",
//               flexWrap: "wrap",
//               marginBottom: "10px",
//             }}
//           >
//             <span style={{ fontSize: "28px" }}>
//               {getStatusEmoji(objectStatus, lidarData?.box_info)}
//             </span>
//             <span style={{ fontWeight: "bold", fontSize: "18px" }}>
//               {statusText}
//             </span>

//             {/* ⭐ ТИП КОРОБКИ С РАЗМЕРАМИ */}
//             {lidarData?.box_info?.detected &&
//               lidarData.box_info.vehicle_type === "box" && (
//                 <span
//                   style={{
//                     padding: "4px 14px",
//                     borderRadius: "16px",
//                     backgroundColor: getBoxColor(lidarData.box_info.box_type),
//                     color: "white",
//                     fontSize: "15px",
//                     fontWeight: "bold",
//                     display: "inline-flex",
//                     alignItems: "center",
//                     gap: "6px",
//                   }}
//                 >
//                   {/* ⭐ ТОЛЬКО БУКВА S/M/L */}
//                   <span>{getBoxLabel(lidarData.box_info.box_type)}</span>
//                   <span style={{ fontSize: "13px", opacity: 0.85 }}>
//                     {lidarData.box_info.size_cm.width}×
//                     {lidarData.box_info.size_cm.depth}×
//                     {lidarData.box_info.size_cm.height}см
//                   </span>
//                   <span style={{ fontSize: "12px", opacity: 0.7 }}>
//                     {lidarData.box_info.confidence}%
//                   </span>
//                 </span>
//               )}

//             {/* Грузовик */}
//             {lidarData?.profile && lidarData.object_type === "truck" && (
//               <span style={{ fontSize: "15px", opacity: 0.85 }}>
//                 🚛 {lidarData.profile.name}
//                 <span style={{ fontSize: "13px", opacity: 0.6 }}>
//                   {" "}
//                   {lidarData.profile_confidence}%
//                 </span>
//               </span>
//             )}

//             <span
//               style={{ fontSize: "14px", opacity: 0.5, marginLeft: "auto" }}
//             >
//               {status?.connected ? "📡" : "📡❌"}
//               {cameraStatus?.connected ? " 📷" : " 📷❌"}
//             </span>
//           </div>

//           {/* Ряд 2: Параметры сканирования */}
//           <div
//             style={{
//               display: "flex",
//               alignItems: "center",
//               gap: "16px",
//               flexWrap: "wrap",
//               paddingTop: "8px",
//               borderTop: `1px solid ${statusColor}30`,
//               fontSize: "14px",
//               opacity: 0.85,
//             }}
//           >
//             {objectStatus !== "no_object" &&
//               objectStatus !== "no_data" &&
//               lidarData && (
//                 <>
//                   <span>
//                     📍 <strong>{lidarData.points_count}</strong> точек
//                   </span>
//                   <span>
//                     📏 <strong>{lidarData.object_height_mm || 0}</strong> мм
//                   </span>
//                   {lidarData.spread_mm && (
//                     <span>
//                       ↔ <strong>{lidarData.spread_mm}</strong> мм
//                     </span>
//                   )}
//                   {lidarData.box_info?.detected && (
//                     <span>
//                       📦 <strong>{lidarData.box_info.box_label}</strong>
//                     </span>
//                   )}
//                   {lidarData.floor_level_mm && (
//                     <span>
//                       🏗️ пол <strong>{lidarData.floor_level_mm}</strong> мм
//                     </span>
//                   )}
//                 </>
//               )}
//             {objectStatus === "no_object" && (
//               <span style={{ fontSize: "16px" }}>
//                 📭 Объект не обнаружен - поместите коробку или автомобиль под
//                 лидар
//               </span>
//             )}
//           </div>

//           {/* ⭐ Ряд 3: ОБЪЕМ КОРОБКИ + Объем угля + Масса + Уверенность + Время */}
//           <div
//             style={{
//               display: "flex",
//               alignItems: "center",
//               gap: "16px",
//               flexWrap: "wrap",
//               paddingTop: "8px",
//               borderTop: `1px solid ${statusColor}30`,
//               fontSize: "14px",
//               opacity: 0.85,
//             }}
//           >
//             {/* ⭐ ОБЪЕМ КОРОБКИ (из box_info) */}
//             {lidarData?.box_info?.detected &&
//               lidarData.box_info.vehicle_type === "box" && (
//                 <span
//                   style={{
//                     padding: "2px 12px",
//                     borderRadius: "12px",
//                     backgroundColor: "#2196F330",
//                     color: "#1976D2",
//                     fontWeight: "bold",
//                     fontSize: "14px",
//                   }}
//                 >
//                   📐{" "}
//                   {(lidarData.box_info.size_cm.width *
//                     lidarData.box_info.size_cm.depth *
//                     lidarData.box_info.size_cm.height) /
//                     1000}{" "}
//                   л
//                 </span>
//               )}

//             {/* Объем угля (2D) */}
//             {volumeData &&
//               !emptyStatus?.is_empty &&
//               emptyStatus?.object_status !== "no_object" && (
//                 <>
//                   <span
//                     style={{
//                       fontSize: "16px",
//                       fontWeight: "bold",
//                       color: statusColor,
//                     }}
//                   >
//                     📦 {volumeData.volume_m3} м³
//                   </span>
//                   <span>
//                     ⚖️ <strong>{volumeData.coal_mass_tons}</strong> т
//                   </span>
//                   <span>
//                     📐 <strong>{volumeData.cross_section_area}</strong> м²
//                   </span>
//                   <span>
//                     📈 <strong>{volumeData.avg_height_m}</strong> м
//                   </span>
//                 </>
//               )}

//             {!volumeData &&
//               !emptyStatus?.is_empty &&
//               emptyStatus?.object_status !== "no_object" && (
//                 <span style={{ opacity: 0.6 }}>⏳ Расчет объема...</span>
//               )}

//             {/* Уверенность */}
//             {emptyStatus && (
//               <span
//                 style={{
//                   marginLeft: "auto",
//                   padding: "4px 12px",
//                   borderRadius: "12px",
//                   backgroundColor: emptyStatus.is_empty
//                     ? "#ff6b6b30"
//                     : "#51cf6630",
//                   color: emptyStatus.is_empty ? "#c92a2a" : "#2f9e44",
//                   fontWeight: "bold",
//                   fontSize: "14px",
//                 }}
//               >
//                 {emptyStatus.is_empty ? "🔴 ПУСТ" : "🟢 ЗАПОЛНЕН"}{" "}
//                 {emptyStatus.confidence}%
//               </span>
//             )}

//             {/* Время */}
//             {lidarData && (
//               <span style={{ fontSize: "12px", opacity: 0.5 }}>
//                 🕐 {new Date(lidarData.timestamp).toLocaleTimeString()}
//               </span>
//             )}
//           </div>
//         </div>
//       )}
//       {/* ═══════════════════════════════════════════════════════════ */}
//       {/* КОНЕЦ ЕДИНОГО БЛОКА */}
//       {/* ═══════════════════════════════════════════════════════════ */}

//       {error && (
//         <div
//           style={{
//             marginBottom: "12px",
//             padding: "8px 14px",
//             backgroundColor: "#f8d7da",
//             color: "#721c24",
//             borderRadius: "4px",
//             fontSize: "14px",
//           }}
//         >
//           ⚠️ {error}
//         </div>
//       )}
//       {success && (
//         <div
//           style={{
//             marginBottom: "12px",
//             padding: "8px 14px",
//             backgroundColor: "#d4edda",
//             color: "#155724",
//             borderRadius: "4px",
//             fontSize: "14px",
//           }}
//         >
//           ✅ {success}
//         </div>
//       )}

//       {/* 3D прогресс */}
//       {isScanning && (
//         <div
//           style={{
//             marginBottom: "12px",
//             padding: "10px 16px",
//             backgroundColor: "white",
//             borderRadius: "6px",
//           }}
//         >
//           <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
//             <div
//               style={{
//                 flex: 1,
//                 height: "6px",
//                 backgroundColor: "#e0e0e0",
//                 borderRadius: "3px",
//                 overflow: "hidden",
//               }}
//             >
//               <div
//                 style={{
//                   width: `${scanProgress}%`,
//                   height: "100%",
//                   backgroundColor: "#007bff",
//                   transition: "width 0.3s",
//                 }}
//               />
//             </div>
//             <span
//               style={{ fontSize: "13px", fontWeight: "bold", color: "#007bff" }}
//             >
//               {Math.round(scanProgress)}%
//             </span>
//             <span style={{ fontSize: "12px", color: "#666" }}>
//               {scanProfiles.length} профилей
//             </span>
//             {totalVolume3d !== null && (
//               <span
//                 style={{
//                   fontSize: "15px",
//                   fontWeight: "bold",
//                   color: "#764ba2",
//                 }}
//               >
//                 📦 {totalVolume3d} м³
//               </span>
//             )}
//           </div>
//         </div>
//       )}

//       <div
//         style={{
//           display: "grid",
//           gridTemplateColumns: showCamera ? "1fr 1fr" : "1fr",
//           gap: "16px",
//         }}
//       >
//         {/* Левая колонка - Лидар */}
//         <div>
//           <div
//             style={{
//               backgroundColor: "white",
//               borderRadius: "8px",
//               padding: "12px",
//               marginBottom: "12px",
//               position: "relative",
//             }}
//           >
//             <h3 style={{ margin: 0, marginBottom: "10px", fontSize: "16px" }}>
//               📡 Сканирование
//             </h3>
//             <canvas
//               ref={canvasRef}
//               width={500}
//               height={500}
//               style={{
//                 width: "100%",
//                 maxWidth: "500px",
//                 height: "auto",
//                 border: "1px solid #ddd",
//                 borderRadius: "4px",
//                 display: "block",
//                 margin: "0 auto",
//               }}
//             />

//             {showObjectMessage && (
//               <div
//                 style={{
//                   position: "absolute",
//                   top: "50%",
//                   left: "50%",
//                   transform: "translate(-50%, -50%)",
//                   textAlign: "center",
//                   pointerEvents: "none",
//                   backgroundColor: "rgba(0,0,0,0.75)",
//                   padding: "20px 30px",
//                   borderRadius: "12px",
//                   border: "2px solid #888",
//                 }}
//               >
//                 <div style={{ fontSize: "48px" }}>📭</div>
//                 <div
//                   style={{
//                     fontSize: "20px",
//                     fontWeight: "bold",
//                     color: "#fff",
//                   }}
//                 >
//                   Объект отсутствует
//                 </div>
//                 <div
//                   style={{ fontSize: "14px", color: "#aaa", marginTop: "4px" }}
//                 >
//                   Поместите объект под лидар
//                 </div>
//               </div>
//             )}

//             <div
//               style={{
//                 fontSize: "11px",
//                 color: "#888",
//                 marginTop: "6px",
//                 textAlign: "center",
//               }}
//             >
//               🟢 &gt;3м &nbsp; 🟡 1-3м &nbsp; 🔴 &lt;1м &nbsp; | &nbsp; 70°
//               сектор (-35°…+35°)
//             </div>
//           </div>

//           {/* График профиля */}
//           {lidarData &&
//             lidarData.distances_m &&
//             lidarData.distances_m.length > 0 &&
//             !showObjectMessage && (
//               <div
//                 style={{
//                   padding: "10px 12px",
//                   backgroundColor: "white",
//                   borderRadius: "4px",
//                 }}
//               >
//                 <div
//                   style={{
//                     fontSize: "13px",
//                     color: "#666",
//                     marginBottom: "6px",
//                   }}
//                 >
//                   📈 Профиль расстояний
//                 </div>
//                 <canvas
//                   ref={chartCanvasRef}
//                   width={600}
//                   height={100}
//                   style={{
//                     width: "100%",
//                     height: "100px",
//                     border: "1px solid #ddd",
//                     borderRadius: "4px",
//                   }}
//                 />
//                 <div
//                   style={{ fontSize: "10px", color: "#999", marginTop: "4px" }}
//                 >
//                   🔴 Уровень борта (3м) — выше = уголь, ниже = пусто
//                 </div>
//               </div>
//             )}
//         </div>

//         {/* Правая колонка - Камера */}
//         {showCamera && (
//           <div>
//             <div
//               style={{
//                 backgroundColor: "white",
//                 borderRadius: "8px",
//                 padding: "12px",
//               }}
//             >
//               <h3 style={{ margin: 0, marginBottom: "10px", fontSize: "16px" }}>
//                 📷 Контроль качества
//               </h3>
//               {cameraLoading && (
//                 <div
//                   style={{
//                     textAlign: "center",
//                     padding: "20px",
//                     fontSize: "14px",
//                     color: "#666",
//                   }}
//                 >
//                   Загрузка кадра...
//                 </div>
//               )}
//               {cameraImage && !cameraLoading && (
//                 <img
//                   src={cameraImage}
//                   alt="Camera"
//                   style={{
//                     width: "100%",
//                     borderRadius: "4px",
//                     border: "1px solid #ddd",
//                   }}
//                 />
//               )}
//               {!cameraImage && !cameraLoading && (
//                 <div
//                   style={{
//                     textAlign: "center",
//                     padding: "30px",
//                     color: "#999",
//                     background: "#f9f9f9",
//                     borderRadius: "4px",
//                     fontSize: "14px",
//                   }}
//                 >
//                   📷 Нет изображения с камеры
//                   <br />
//                   <span style={{ fontSize: "12px", color: "#bbb" }}>
//                     Проверьте подключение
//                   </span>
//                 </div>
//               )}
//               <div
//                 style={{
//                   fontSize: "12px",
//                   color: "#888",
//                   marginTop: "8px",
//                   textAlign: "center",
//                 }}
//               >
//                 {cameraStatus?.connected
//                   ? "✅ Камера работает"
//                   : "⏳ Ожидание подключения"}
//               </div>
//             </div>
//           </div>
//         )}
//       </div>

//       {/* История измерений */}
//       {showHistory && (
//         <div
//           style={{
//             marginTop: "16px",
//             padding: "12px 16px",
//             backgroundColor: "white",
//             borderRadius: "6px",
//           }}
//         >
//           <div
//             style={{
//               display: "flex",
//               justifyContent: "space-between",
//               alignItems: "center",
//               marginBottom: "10px",
//             }}
//           >
//             <span style={{ fontSize: "15px", fontWeight: "bold" }}>
//               📋 История измерений
//             </span>
//             <span style={{ fontSize: "12px", color: "#888" }}>
//               {measurements.length} записей
//             </span>
//           </div>
//           {measurements.length === 0 ? (
//             <div
//               style={{
//                 textAlign: "center",
//                 padding: "12px",
//                 color: "#999",
//                 fontSize: "14px",
//               }}
//             >
//               Нет сохранённых измерений
//             </div>
//           ) : (
//             <div style={{ overflowX: "auto", fontSize: "13px" }}>
//               <table style={{ width: "100%", borderCollapse: "collapse" }}>
//                 <thead>
//                   <tr style={{ backgroundColor: "#f5f5f5" }}>
//                     <th
//                       style={{
//                         padding: "6px 10px",
//                         border: "1px solid #ddd",
//                         textAlign: "left",
//                       }}
//                     >
//                       ID
//                     </th>
//                     <th
//                       style={{
//                         padding: "6px 10px",
//                         border: "1px solid #ddd",
//                         textAlign: "left",
//                       }}
//                     >
//                       Дата/время
//                     </th>
//                     <th
//                       style={{
//                         padding: "6px 10px",
//                         border: "1px solid #ddd",
//                         textAlign: "right",
//                       }}
//                     >
//                       Объём (м³)
//                     </th>
//                     <th
//                       style={{
//                         padding: "6px 10px",
//                         border: "1px solid #ddd",
//                         textAlign: "right",
//                       }}
//                     >
//                       Масса (т)
//                     </th>
//                     <th
//                       style={{
//                         padding: "6px 10px",
//                         border: "1px solid #ddd",
//                         textAlign: "center",
//                       }}
//                     >
//                       Статус
//                     </th>
//                   </tr>
//                 </thead>
//                 <tbody>
//                   {measurements.slice(0, 10).map((m) => (
//                     <tr key={m.id}>
//                       <td
//                         style={{
//                           padding: "4px 10px",
//                           border: "1px solid #ddd",
//                         }}
//                       >
//                         {m.id}
//                       </td>
//                       <td
//                         style={{
//                           padding: "4px 10px",
//                           border: "1px solid #ddd",
//                           fontSize: "12px",
//                         }}
//                       >
//                         {new Date(m.timestamp).toLocaleString()}
//                       </td>
//                       <td
//                         style={{
//                           padding: "4px 10px",
//                           border: "1px solid #ddd",
//                           textAlign: "right",
//                         }}
//                       >
//                         {m.volume_m3}
//                       </td>
//                       <td
//                         style={{
//                           padding: "4px 10px",
//                           border: "1px solid #ddd",
//                           textAlign: "right",
//                         }}
//                       >
//                         {m.mass_tons}
//                       </td>
//                       <td
//                         style={{
//                           padding: "4px 10px",
//                           border: "1px solid #ddd",
//                           textAlign: "center",
//                           color: m.is_empty ? "#dc3545" : "#28a745",
//                           fontWeight: "bold",
//                         }}
//                       >
//                         {m.is_empty ? "📭 ПУСТ" : "📦 ЗАПОЛНЕН"}
//                       </td>
//                     </tr>
//                   ))}
//                 </tbody>
//               </table>
//               {measurements.length > 10 && (
//                 <div
//                   style={{
//                     textAlign: "center",
//                     fontSize: "12px",
//                     color: "#888",
//                     marginTop: "6px",
//                   }}
//                 >
//                   + еще {measurements.length - 10} записей
//                 </div>
//               )}
//             </div>
//           )}
//         </div>
//       )}

//       {/* Настройки автомобиля */}
//       <details style={{ marginTop: "12px" }}>
//         <summary
//           style={{
//             cursor: "pointer",
//             color: "#666",
//             fontSize: "13px",
//             padding: "4px 0",
//           }}
//         >
//           ⚙️ Настройки автомобиля
//         </summary>
//         <div
//           style={{
//             marginTop: "8px",
//             padding: "12px 16px",
//             backgroundColor: "white",
//             borderRadius: "4px",
//           }}
//         >
//           <div
//             style={{
//               display: "grid",
//               gridTemplateColumns: "repeat(3, 1fr)",
//               gap: "12px",
//             }}
//           >
//             <div>
//               <label
//                 style={{
//                   fontSize: "12px",
//                   color: "#666",
//                   display: "block",
//                   marginBottom: "4px",
//                 }}
//               >
//                 📏 Длина кузова (м)
//               </label>
//               <input
//                 type="number"
//                 step="0.5"
//                 value={vehicleParams.length_m}
//                 onChange={(e) =>
//                   setVehicleParams({
//                     ...vehicleParams,
//                     length_m: parseFloat(e.target.value),
//                   })
//                 }
//                 style={{
//                   width: "100%",
//                   padding: "4px 8px",
//                   fontSize: "14px",
//                   border: "1px solid #ddd",
//                   borderRadius: "4px",
//                 }}
//               />
//             </div>
//             <div>
//               <label
//                 style={{
//                   fontSize: "12px",
//                   color: "#666",
//                   display: "block",
//                   marginBottom: "4px",
//                 }}
//               >
//                 📐 Ширина кузова (м)
//               </label>
//               <input
//                 type="number"
//                 step="0.1"
//                 value={vehicleParams.width_m}
//                 onChange={(e) =>
//                   setVehicleParams({
//                     ...vehicleParams,
//                     width_m: parseFloat(e.target.value),
//                   })
//                 }
//                 style={{
//                   width: "100%",
//                   padding: "4px 8px",
//                   fontSize: "14px",
//                   border: "1px solid #ddd",
//                   borderRadius: "4px",
//                 }}
//               />
//             </div>
//             <div>
//               <label
//                 style={{
//                   fontSize: "12px",
//                   color: "#666",
//                   display: "block",
//                   marginBottom: "4px",
//                 }}
//               >
//                 ⚫ Плотность угля (кг/м³)
//               </label>
//               <input
//                 type="number"
//                 step="10"
//                 value={vehicleParams.coal_density_kg_m3}
//                 onChange={(e) =>
//                   setVehicleParams({
//                     ...vehicleParams,
//                     coal_density_kg_m3: parseFloat(e.target.value),
//                   })
//                 }
//                 style={{
//                   width: "100%",
//                   padding: "4px 8px",
//                   fontSize: "14px",
//                   border: "1px solid #ddd",
//                   borderRadius: "4px",
//                 }}
//               />
//             </div>
//           </div>
//           <div style={{ fontSize: "11px", color: "#999", marginTop: "8px" }}>
//             💡 Укажите реальные размеры кузова для точного расчёта
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

// ⭐ ИНТЕРФЕЙС ДЛЯ BOX_INFO
interface BoxInfo {
  box_type: string; // "small" | "medium" | "large" | "unknown" | "none"
  box_label: string; // "S" | "M" | "L" | "?" | "-"
  box_name: string; // "Малая" | "Средняя" | "Большая"
  emoji?: string;
  size_mm: {
    width: number;
    depth: number;
    height: number;
  };
  size_cm: {
    width: number;
    depth: number;
    height: number;
  };
  detected: boolean;
  confidence: number;
  profile_name?: string;
  vehicle_type?: string;
  brand?: string;
  model?: string;
  profile_confidence?: number;
}

// ⭐ ИНТЕРФЕЙС ДЛЯ ОБЪЕМА (С БЭКЕНДА)
interface VolumeInfo {
  volume_m3: number;
  mass_tons: number;
  height_mm: number;
  fill_percent: number;
  cross_section_m2: number;
  points_used: number;
  raw_volume_m3: number;
  calibration_factor: number;
}

interface LidarData {
  timestamp: string;
  points_count: number;
  distances_mm: number[];
  distances_m: number[];
  scan_geometry?: {
    start_angle_deg: number;
    stop_angle_deg: number;
    angular_step_deg: number;
    points_count: number;
    total_angle_deg: number;
    source: string;
  };
  statistics: {
    min_mm: number;
    max_mm: number;
    avg_mm: number;
    min_m: number;
    max_m: number;
    avg_m: number;
  };
  object_status?: string;
  status_text?: string;
  object_detected?: boolean;
  is_empty?: boolean;
  empty_confidence?: number;
  object_type?: string;
  object_height_mm?: number;
  floor_level_mm?: number;
  spread_mm?: number;
  box_info?: BoxInfo;
  volume_info?: VolumeInfo; // ⭐ ДАННЫЕ С БЭКЕНДА
  profile?: any;
  profile_confidence?: number;
  reason?: string;
}

interface CameraStatus {
  connected: boolean;
  type: string;
  ip?: string;
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
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showCamera, setShowCamera] = useState(true);
  const [measurements, setMeasurements] = useState<SavedMeasurement[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartCanvasRef = useRef<HTMLCanvasElement>(null);

  const [objectStatus, setObjectStatus] = useState<string>("unknown");
  const [statusText, setStatusText] = useState<string>("⏳ Ожидание данных...");
  const [statusColor, setStatusColor] = useState<string>("#2196F3");
  const [showObjectMessage, setShowObjectMessage] = useState<boolean>(false);
  const [emptyStatus, setEmptyStatus] = useState<{
    is_empty: boolean;
    confidence: number;
    reason: string;
    points_count: number;
    object_status?: string;
    status_description?: string;
  } | null>(null);

  // 3D сканирование
  const [isScanning, setIsScanning] = useState(false);
  const [scanProfiles, setScanProfiles] = useState<ScanProfile[]>([]);
  const [totalVolume3d, setTotalVolume3d] = useState<number | null>(null);
  const [scanProgress, setScanProgress] = useState(0);
  const scanIntervalRef = useRef<number | undefined>(undefined);
  const startTimeRef = useRef<number>(0);
  const [currentScanId, setCurrentScanId] = useState<string | null>(null);
  const isScanningRef = useRef(false);

  const [vehicleParams, setVehicleParams] = useState({
    length_m: 6.0,
    width_m: 2.5,
    coal_density_kg_m3: 850,
  });

  // ⭐ ФУНКЦИИ ДЛЯ ОТОБРАЖЕНИЯ
  const getBoxColor = (boxType: string): string => {
    switch (boxType) {
      case "small":
        return "#4CAF50";
      case "medium":
        return "#FF9800";
      case "large":
        return "#F44336";
      case "none":
        return "#9E9E9E";
      default:
        return "#9E9E9E";
    }
  };

  const getBoxLabel = (boxType: string): string => {
    switch (boxType) {
      case "small":
        return "S";
      case "medium":
        return "M";
      case "large":
        return "L";
      default:
        return "?";
    }
  };

  const getStatusEmoji = (objectStatus: string, boxInfo?: BoxInfo): string => {
    if (objectStatus === "no_object" || objectStatus === "no_data") return "📭";
    if (boxInfo?.detected && boxInfo.vehicle_type === "box") {
      return boxInfo.emoji || "📦";
    }
    if (objectStatus === "filled") return "📦✅";
    if (objectStatus === "empty") return "📦";
    return "📡";
  };

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

  const fetchMeasurements = async () => {
    try {
      const response = await lidarApi.getMeasurements(20);
      setMeasurements(response.data);
    } catch (err) {
      console.error("Error fetching measurements:", err);
    }
  };

  // ========== 3D СКАНИРОВАНИЕ ==========
  const start3DScan = async () => {
    console.log("🚀 1. start3DScan вызван");

    try {
      const response = await scan3dApi.start(
        vehicleParams.length_m,
        vehicleParams.width_m,
      );
      const scanId = response.data.scan_id;

      console.log("✅ 2. Сессия создана на бэкенде, scanId:", scanId);

      setCurrentScanId(scanId);
      setIsScanning(true);
      isScanningRef.current = true;
      setScanProfiles([]);
      setTotalVolume3d(null);
      setScanProgress(0);
      startTimeRef.current = Date.now();

      if (scanIntervalRef.current) {
        clearInterval(scanIntervalRef.current);
      }

      scanIntervalRef.current = window.setInterval(async () => {
        if (!isScanningRef.current) {
          console.log("⏸️ Сканирование остановлено");
          return;
        }

        try {
          const scanResponse = await lidarApi.getScan();
          const data = scanResponse.data;

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
              ? validHeights.reduce((a: number, b: number) => a + b, 0) /
                validHeights.length
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

            setScanProgress(
              Math.min(100, (position / vehicleParams.length_m) * 100),
            );
          }
        } catch (err) {
          console.error("❌ Ошибка в интервале:", err);
        }
      }, 100);
    } catch (error) {
      console.error("❌ Ошибка при старте сканирования:", error);
      setError("Не удалось начать 3D сканирование");
    }
  };

  const stop3DScan = async () => {
    console.log("⏹️ Остановка 3D сканирования, ID:", currentScanId);

    isScanningRef.current = false;
    setIsScanning(false);

    if (scanIntervalRef.current) {
      clearInterval(scanIntervalRef.current);
      scanIntervalRef.current = undefined;
    }

    if (currentScanId) {
      try {
        const response = await scan3dApi.stop(currentScanId);
        const result = response.data;
        console.log("📦 Результат 3D:", result);

        setTotalVolume3d(result.total_volume_m3);
        setSuccess(
          `3D сканирование завершено! Объём: ${result.total_volume_m3} м³, Масса: ${result.total_mass_tons} т`,
        );

        await fetchMeasurements();
        console.log("📋 История обновлена");
      } catch (err: any) {
        console.error("Error stopping 3D scan:", err);
        setError(
          err.response?.data?.detail || "Ошибка при завершении 3D сканирования",
        );
      }
    } else {
      console.warn("Нет active scanId для остановки");
    }
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
        coal_density_kg_m3: vehicleParams.coal_density_kg_m3,
      });

      setSuccess(
        `Измерение сохранено! Объём: ${response.data.volume_m3} м³, Масса: ${response.data.mass_tons} т`,
      );

      setLidarData({
        timestamp: response.data.timestamp,
        points_count: response.data.points_count,
        distances_mm: response.data.distances_mm,
        distances_m: response.data.distances_mm.map((d: number) => d / 1000),
        statistics: {
          min_mm: Math.min(...response.data.distances_mm),
          max_mm: Math.max(...response.data.distances_mm),
          avg_mm:
            response.data.distances_mm.reduce(
              (a: number, b: number) => a + b,
              0,
            ) / response.data.distances_mm.length,
          min_m: Math.min(...response.data.distances_mm) / 1000,
          max_m: Math.max(...response.data.distances_mm) / 1000,
          avg_m:
            response.data.distances_mm.reduce(
              (a: number, b: number) => a + b,
              0,
            ) /
            response.data.distances_mm.length /
            1000,
        },
        box_info: response.data.box_info,
        volume_info: response.data.volume_info,
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
            avg_mm:
              response.data.distances_mm.reduce(
                (a: number, b: number) => a + b,
                0,
              ) / response.data.distances_mm.length,
            min_m: Math.min(...response.data.distances_mm) / 1000,
            max_m: Math.max(...response.data.distances_mm) / 1000,
            avg_m:
              response.data.distances_mm.reduce(
                (a: number, b: number) => a + b,
                0,
              ) /
              response.data.distances_mm.length /
              1000,
          },
          box_info: response.data.box_info,
          volume_info: response.data.volume_info,
        });
        drawDistanceChart({
          distances_mm: response.data.distances_mm,
          distances_m: response.data.distances_mm.map((d: number) => d / 1000),
          points_count: response.data.points_count,
          timestamp: response.data.timestamp,
          statistics: {
            min_mm: Math.min(...response.data.distances_mm),
            max_mm: Math.max(...response.data.distances_mm),
            avg_mm:
              response.data.distances_mm.reduce(
                (a: number, b: number) => a + b,
                0,
              ) / response.data.distances_mm.length,
            min_m: Math.min(...response.data.distances_mm) / 1000,
            max_m: Math.max(...response.data.distances_mm) / 1000,
            avg_m:
              response.data.distances_mm.reduce(
                (a: number, b: number) => a + b,
                0,
              ) /
              response.data.distances_mm.length /
              1000,
          },
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
      const data = response.data;
      console.log("📦 Данные с бэкенда:", data);
      console.log("📦 box_info:", data.box_info);
      console.log("📦 volume_info:", data.volume_info);

      setLidarData(data);

      const objectStatus = data.object_status || "unknown";
      const statusText = data.status_text || "Неизвестно";
      const isEmpty = data.is_empty !== undefined ? data.is_empty : true;

      setObjectStatus(objectStatus);
      setStatusText(statusText);

      if (objectStatus === "no_object" || objectStatus === "no_data") {
        setShowObjectMessage(true);
        setStatusColor("#888888");
        const canvas = canvasRef.current;
        if (canvas) {
          const ctx = canvas.getContext("2d");
          if (ctx) {
            ctx.fillStyle = "#1a1a1a";
            ctx.fillRect(0, 0, canvas.width, canvas.height);
          }
        }
      } else {
        setShowObjectMessage(false);
        if (objectStatus === "empty" || isEmpty) {
          setStatusColor("#FF9800");
        } else if (objectStatus === "filled") {
          setStatusColor("#4CAF50");
        } else {
          setStatusColor("#2196F3");
        }
      }

      setEmptyStatus({
        is_empty: isEmpty,
        confidence: data.empty_confidence || 80,
        reason: data.reason || statusText || "Статус от бэкенда",
        points_count: data.points_count || 0,
        object_status: objectStatus,
        status_description: statusText,
      });

      if (
        data.distances_mm &&
        data.distances_mm.length > 0 &&
        objectStatus !== "no_object"
      ) {
        drawLidarData(data);
        drawDistanceChart(data);
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

  const draw3DHeatmap = () => {
    const canvas = canvasRef.current;
    if (!canvas || scanProfiles.length === 0) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;

    ctx.fillStyle = "#1a1a1a";
    ctx.fillRect(0, 0, width, height);

    const allHeights = scanProfiles.map(
      (p) => p.cross_section_m2 / vehicleParams.width_m,
    );
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

    const startAngleDeg = data.scan_geometry?.start_angle_deg ?? -5;
    const stopAngleDeg = data.scan_geometry?.stop_angle_deg ?? 185;
    const totalAngleDeg =
      data.scan_geometry?.total_angle_deg ?? stopAngleDeg - startAngleDeg;

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
    ctx.fillText(`${startAngleDeg.toFixed(1)}°`, leftX - 15, leftY);
    ctx.fillText(`${stopAngleDeg.toFixed(1)}°`, rightX + 5, rightY - 5);
    ctx.fillText(`${totalAngleDeg.toFixed(1)}° сектор`, centerX + 20, centerY - maxRadius * 0.75);

    const firstGridAngle = Math.ceil(startAngleDeg / 30) * 30;
    for (let angle = firstGridAngle; angle <= stopAngleDeg; angle += 30) {
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

    const sectorAngleDeg = totalAngleDeg;
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
    ctx.fillText(
      `Сектор сканирования: ${totalAngleDeg.toFixed(1)}° ` +
        `(от ${startAngleDeg.toFixed(1)}° до ${stopAngleDeg.toFixed(1)}°)`,
      centerX,
      height - 10,
    );
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
    fetchStatus();
    fetchCameraStatus();
    fetchLidarData();
    fetchMeasurements();

    const autoRefreshInterval = setInterval(() => {
      fetchLidarData();
    }, 2000);

    return () => {
      clearInterval(autoRefreshInterval);
    };
  }, []);

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

  // ⭐ ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ ОБЪЕМА КОРОБКИ
  const getBoxVolumeLiters = (boxInfo?: BoxInfo): number => {
    if (!boxInfo?.detected || boxInfo.vehicle_type !== "box") return 0;
    const { width, depth, height } = boxInfo.size_cm;
    return Math.round((width * depth * height) / 1000);
  };

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
        <h2 style={{ margin: 0, fontSize: "22px" }}>📊 Уголь-Контроль</h2>
        <div
          style={{
            display: "flex",
            gap: "8px",
            alignItems: "center",
            flexWrap: "wrap",
          }}
        >
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: "4px",
              fontSize: "13px",
            }}
          >
            <input
              type="checkbox"
              checked={showCamera}
              onChange={(e) => setShowCamera(e.target.checked)}
            />
            📷
          </label>
          <button
            onClick={fetchLidarData}
            disabled={loading}
            style={{
              padding: "6px 14px",
              backgroundColor: "#6c757d",
              color: "white",
              border: "none",
              borderRadius: "4px",
              cursor: loading ? "not-allowed" : "pointer",
              fontSize: "13px",
            }}
          >
            {loading ? "..." : "🔄"}
          </button>
          <button
            onClick={performMeasurement}
            disabled={saving}
            style={{
              padding: "6px 14px",
              backgroundColor: "#28a745",
              color: "white",
              border: "none",
              borderRadius: "4px",
              cursor: saving ? "not-allowed" : "pointer",
              fontSize: "13px",
            }}
          >
            {saving ? "..." : "📐"}
          </button>
          {!isScanning ? (
            <button
              onClick={start3DScan}
              style={{
                padding: "6px 14px",
                backgroundColor: "#007bff",
                color: "white",
                border: "none",
                borderRadius: "4px",
                cursor: "pointer",
                fontSize: "13px",
              }}
            >
              🚀3D
            </button>
          ) : (
            <button
              onClick={stop3DScan}
              style={{
                padding: "6px 14px",
                backgroundColor: "#dc3545",
                color: "white",
                border: "none",
                borderRadius: "4px",
                cursor: "pointer",
                fontSize: "13px",
              }}
            >
              ⏹
            </button>
          )}
          <button
            onClick={() => setShowHistory(!showHistory)}
            style={{
              padding: "6px 14px",
              backgroundColor: "#17a2b8",
              color: "white",
              border: "none",
              borderRadius: "4px",
              cursor: "pointer",
              fontSize: "13px",
            }}
          >
            {showHistory ? "📕" : "📋"}
          </button>
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════ */}
      {/* ⭐ ЕДИНЫЙ БОЛЬШОЙ БЛОК - ВСЯ ИНФОРМАЦИЯ В ОДНОМ МЕСТЕ */}
      {/* ═══════════════════════════════════════════════════════════ */}
      {statusText && (
        <div
          style={{
            padding: "16px 20px",
            borderRadius: "10px",
            backgroundColor: statusColor + "15",
            border: `2px solid ${statusColor}`,
            color: statusColor,
            marginBottom: "16px",
            fontSize: "15px",
          }}
        >
          {/* Ряд 1: Статус + Тип + Размеры + Подключения */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "12px",
              flexWrap: "wrap",
              marginBottom: "10px",
            }}
          >
            <span style={{ fontSize: "28px" }}>
              {getStatusEmoji(objectStatus, lidarData?.box_info)}
            </span>
            <span style={{ fontWeight: "bold", fontSize: "18px" }}>
              {statusText}
            </span>

            {/* ⭐ ТИП КОРОБКИ С РАЗМЕРАМИ */}
            {lidarData?.box_info?.detected &&
              lidarData.box_info.vehicle_type === "box" && (
                <span
                  style={{
                    padding: "4px 14px",
                    borderRadius: "16px",
                    backgroundColor: getBoxColor(lidarData.box_info.box_type),
                    color: "white",
                    fontSize: "15px",
                    fontWeight: "bold",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "6px",
                  }}
                >
                  <span>{getBoxLabel(lidarData.box_info.box_type)}</span>
                  <span style={{ fontSize: "13px", opacity: 0.85 }}>
                    {lidarData.box_info.size_cm.width}×
                    {lidarData.box_info.size_cm.depth}×
                    {lidarData.box_info.size_cm.height}см
                  </span>
                  <span style={{ fontSize: "12px", opacity: 0.7 }}>
                    {lidarData.box_info.confidence}%
                  </span>
                </span>
              )}

            {/* Грузовик */}
            {lidarData?.profile && lidarData.object_type === "truck" && (
              <span style={{ fontSize: "15px", opacity: 0.85 }}>
                🚛 {lidarData.profile.name}
                <span style={{ fontSize: "13px", opacity: 0.6 }}>
                  {" "}
                  {lidarData.profile_confidence}%
                </span>
              </span>
            )}

            <span
              style={{ fontSize: "14px", opacity: 0.5, marginLeft: "auto" }}
            >
              {status?.connected ? "📡" : "📡❌"}
              {cameraStatus?.connected ? " 📷" : " 📷❌"}
            </span>
          </div>

          {/* Ряд 2: Параметры сканирования */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "16px",
              flexWrap: "wrap",
              paddingTop: "8px",
              borderTop: `1px solid ${statusColor}30`,
              fontSize: "14px",
              opacity: 0.85,
            }}
          >
            {objectStatus !== "no_object" &&
              objectStatus !== "no_data" &&
              lidarData && (
                <>
                  <span>
                    📍 <strong>{lidarData.points_count}</strong> точек
                  </span>
                  <span>
                    📏 <strong>{lidarData.object_height_mm || 0}</strong> мм
                  </span>
                  {lidarData.spread_mm && (
                    <span>
                      ↔ <strong>{lidarData.spread_mm}</strong> мм
                    </span>
                  )}
                  {lidarData.box_info?.detected && (
                    <span>
                      📦 <strong>{lidarData.box_info.box_label}</strong>
                    </span>
                  )}
                  {lidarData.floor_level_mm && (
                    <span>
                      🏗️ пол <strong>{lidarData.floor_level_mm}</strong> мм
                    </span>
                  )}
                </>
              )}
            {objectStatus === "no_object" && (
              <span style={{ fontSize: "16px" }}>
                📭 Объект не обнаружен - поместите коробку или автомобиль под
                лидар
              </span>
            )}
          </div>

          {/* ⭐ Ряд 3: ОБЪЕМ КОРОБКИ + ОБЪЕМ УГЛЯ + МАССА + ВЫСОТА + ЗАПОЛНЕНИЕ */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "16px",
              flexWrap: "wrap",
              paddingTop: "8px",
              borderTop: `1px solid ${statusColor}30`,
              fontSize: "14px",
              opacity: 0.85,
            }}
          >
            {/* ⭐ ОБЪЕМ КОРОБКИ (из box_info) */}
            {lidarData?.box_info?.detected &&
              lidarData.box_info.vehicle_type === "box" && (
                <span
                  style={{
                    padding: "2px 12px",
                    borderRadius: "12px",
                    backgroundColor: "#2196F330",
                    color: "#1976D2",
                    fontWeight: "bold",
                    fontSize: "14px",
                  }}
                >
                  📐 {getBoxVolumeLiters(lidarData.box_info)} л
                </span>
              )}

            {/* ⭐ ОБЪЕМ УГЛЯ (из volume_info с бэкенда) */}
            {lidarData?.volume_info &&
              !lidarData.is_empty &&
              objectStatus !== "no_object" && (
                <>
                  <span
                    style={{
                      fontSize: "16px",
                      fontWeight: "bold",
                      color: statusColor,
                    }}
                  >
                    📦 {lidarData.volume_info.volume_m3.toFixed(3)} м³
                  </span>
                  <span>
                    ⚖️ <strong>{lidarData.volume_info.mass_tons.toFixed(3)}</strong> т
                  </span>
                  <span>
                    📏 <strong>{(lidarData.volume_info.height_mm / 1000).toFixed(2)}</strong> м
                  </span>
                  <span
                    style={{
                      padding: "2px 10px",
                      borderRadius: "12px",
                      backgroundColor:
                        lidarData.volume_info.fill_percent > 50
                          ? "#51cf6630"
                          : "#ff6b6b30",
                      color:
                        lidarData.volume_info.fill_percent > 50
                          ? "#2f9e44"
                          : "#c92a2a",
                      fontWeight: "bold",
                    }}
                  >
                    📊 {lidarData.volume_info.fill_percent}%
                  </span>
                </>
              )}

            {!lidarData?.volume_info &&
              !lidarData?.is_empty &&
              objectStatus !== "no_object" && (
                <span style={{ opacity: 0.6 }}>⏳ Расчет объема...</span>
              )}

            {/* Уверенность */}
            {emptyStatus && (
              <span
                style={{
                  marginLeft: "auto",
                  padding: "4px 12px",
                  borderRadius: "12px",
                  backgroundColor: emptyStatus.is_empty
                    ? "#ff6b6b30"
                    : "#51cf6630",
                  color: emptyStatus.is_empty ? "#c92a2a" : "#2f9e44",
                  fontWeight: "bold",
                  fontSize: "14px",
                }}
              >
                {emptyStatus.is_empty ? "🔴 ПУСТ" : "🟢 ЗАПОЛНЕН"}{" "}
                {emptyStatus.confidence}%
              </span>
            )}

            {/* Время */}
            {lidarData && (
              <span style={{ fontSize: "12px", opacity: 0.5 }}>
                🕐 {new Date(lidarData.timestamp).toLocaleTimeString()}
              </span>
            )}
          </div>
        </div>
      )}
      {/* ═══════════════════════════════════════════════════════════ */}
      {/* КОНЕЦ ЕДИНОГО БЛОКА */}
      {/* ═══════════════════════════════════════════════════════════ */}

      {error && (
        <div
          style={{
            marginBottom: "12px",
            padding: "8px 14px",
            backgroundColor: "#f8d7da",
            color: "#721c24",
            borderRadius: "4px",
            fontSize: "14px",
          }}
        >
          ⚠️ {error}
        </div>
      )}
      {success && (
        <div
          style={{
            marginBottom: "12px",
            padding: "8px 14px",
            backgroundColor: "#d4edda",
            color: "#155724",
            borderRadius: "4px",
            fontSize: "14px",
          }}
        >
          ✅ {success}
        </div>
      )}

      {/* 3D прогресс */}
      {isScanning && (
        <div
          style={{
            marginBottom: "12px",
            padding: "10px 16px",
            backgroundColor: "white",
            borderRadius: "6px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <div
              style={{
                flex: 1,
                height: "6px",
                backgroundColor: "#e0e0e0",
                borderRadius: "3px",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  width: `${scanProgress}%`,
                  height: "100%",
                  backgroundColor: "#007bff",
                  transition: "width 0.3s",
                }}
              />
            </div>
            <span
              style={{ fontSize: "13px", fontWeight: "bold", color: "#007bff" }}
            >
              {Math.round(scanProgress)}%
            </span>
            <span style={{ fontSize: "12px", color: "#666" }}>
              {scanProfiles.length} профилей
            </span>
            {totalVolume3d !== null && (
              <span
                style={{
                  fontSize: "15px",
                  fontWeight: "bold",
                  color: "#764ba2",
                }}
              >
                📦 {totalVolume3d.toFixed(3)} м³
              </span>
            )}
          </div>
        </div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: showCamera ? "1fr 1fr" : "1fr",
          gap: "16px",
        }}
      >
        {/* Левая колонка - Лидар */}
        <div>
          <div
            style={{
              backgroundColor: "white",
              borderRadius: "8px",
              padding: "12px",
              marginBottom: "12px",
              position: "relative",
            }}
          >
            <h3 style={{ margin: 0, marginBottom: "10px", fontSize: "16px" }}>
              📡 Сканирование
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

            {showObjectMessage && (
              <div
                style={{
                  position: "absolute",
                  top: "50%",
                  left: "50%",
                  transform: "translate(-50%, -50%)",
                  textAlign: "center",
                  pointerEvents: "none",
                  backgroundColor: "rgba(0,0,0,0.75)",
                  padding: "20px 30px",
                  borderRadius: "12px",
                  border: "2px solid #888",
                }}
              >
                <div style={{ fontSize: "48px" }}>📭</div>
                <div
                  style={{
                    fontSize: "20px",
                    fontWeight: "bold",
                    color: "#fff",
                  }}
                >
                  Объект отсутствует
                </div>
                <div
                  style={{ fontSize: "14px", color: "#aaa", marginTop: "4px" }}
                >
                  Поместите объект под лидар
                </div>
              </div>
            )}

            <div
              style={{
                fontSize: "11px",
                color: "#888",
                marginTop: "6px",
                textAlign: "center",
              }}
            >
              🟢 &gt;3м &nbsp; 🟡 1-3м &nbsp; 🔴 &lt;1м &nbsp; | &nbsp;
              {lidarData?.scan_geometry
                ? ` ${lidarData.scan_geometry.total_angle_deg.toFixed(1)}° сектор ` +
                  `(${lidarData.scan_geometry.start_angle_deg.toFixed(1)}°…` +
                  `${lidarData.scan_geometry.stop_angle_deg.toFixed(1)}°)`
                : " около 190°"}
            </div>
          </div>

          {/* График профиля */}
          {lidarData &&
            lidarData.distances_m &&
            lidarData.distances_m.length > 0 &&
            !showObjectMessage && (
              <div
                style={{
                  padding: "10px 12px",
                  backgroundColor: "white",
                  borderRadius: "4px",
                }}
              >
                <div
                  style={{
                    fontSize: "13px",
                    color: "#666",
                    marginBottom: "6px",
                  }}
                >
                  📈 Профиль расстояний
                </div>
                <canvas
                  ref={chartCanvasRef}
                  width={600}
                  height={100}
                  style={{
                    width: "100%",
                    height: "100px",
                    border: "1px solid #ddd",
                    borderRadius: "4px",
                  }}
                />
                <div
                  style={{ fontSize: "10px", color: "#999", marginTop: "4px" }}
                >
                  🔴 Уровень борта (3м) — выше = уголь, ниже = пусто
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
                padding: "12px",
              }}
            >
              <h3 style={{ margin: 0, marginBottom: "10px", fontSize: "16px" }}>
                📷 Контроль качества
              </h3>
              <img
                src="http://localhost:8000/api/camera/stream"
                alt="Непрерывная трансляция камеры"
                style={{
                  width: "100%",
                  minHeight: "240px",
                  objectFit: "contain",
                  background: "#111",
                  borderRadius: "4px",
                  border: "1px solid #ddd",
                }}
              />              <div
                style={{
                  fontSize: "12px",
                  color: "#888",
                  marginTop: "8px",
                  textAlign: "center",
                }}
              >
                {cameraStatus?.connected
                  ? "✅ Камера работает"
                  : "⏳ Ожидание подключения"}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* История измерений */}
      {showHistory && (
        <div
          style={{
            marginTop: "16px",
            padding: "12px 16px",
            backgroundColor: "white",
            borderRadius: "6px",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "10px",
            }}
          >
            <span style={{ fontSize: "15px", fontWeight: "bold" }}>
              📋 История измерений
            </span>
            <span style={{ fontSize: "12px", color: "#888" }}>
              {measurements.length} записей
            </span>
          </div>
          {measurements.length === 0 ? (
            <div
              style={{
                textAlign: "center",
                padding: "12px",
                color: "#999",
                fontSize: "14px",
              }}
            >
              Нет сохранённых измерений
            </div>
          ) : (
            <div style={{ overflowX: "auto", fontSize: "13px" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ backgroundColor: "#f5f5f5" }}>
                    <th
                      style={{
                        padding: "6px 10px",
                        border: "1px solid #ddd",
                        textAlign: "left",
                      }}
                    >
                      ID
                    </th>
                    <th
                      style={{
                        padding: "6px 10px",
                        border: "1px solid #ddd",
                        textAlign: "left",
                      }}
                    >
                      Дата/время
                    </th>
                    <th
                      style={{
                        padding: "6px 10px",
                        border: "1px solid #ddd",
                        textAlign: "right",
                      }}
                    >
                      Объём (м³)
                    </th>
                    <th
                      style={{
                        padding: "6px 10px",
                        border: "1px solid #ddd",
                        textAlign: "right",
                      }}
                    >
                      Масса (т)
                    </th>
                    <th
                      style={{
                        padding: "6px 10px",
                        border: "1px solid #ddd",
                        textAlign: "center",
                      }}
                    >
                      Статус
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {measurements.slice(0, 10).map((m) => (
                    <tr key={m.id}>
                      <td
                        style={{
                          padding: "4px 10px",
                          border: "1px solid #ddd",
                        }}
                      >
                        {m.id}
                      </td>
                      <td
                        style={{
                          padding: "4px 10px",
                          border: "1px solid #ddd",
                          fontSize: "12px",
                        }}
                      >
                        {new Date(m.timestamp).toLocaleString()}
                      </td>
                      <td
                        style={{
                          padding: "4px 10px",
                          border: "1px solid #ddd",
                          textAlign: "right",
                        }}
                      >
                        {m.volume_m3}
                      </td>
                      <td
                        style={{
                          padding: "4px 10px",
                          border: "1px solid #ddd",
                          textAlign: "right",
                        }}
                      >
                        {m.mass_tons}
                      </td>
                      <td
                        style={{
                          padding: "4px 10px",
                          border: "1px solid #ddd",
                          textAlign: "center",
                          color: m.is_empty ? "#dc3545" : "#28a745",
                          fontWeight: "bold",
                        }}
                      >
                        {m.is_empty ? "📭 ПУСТ" : "📦 ЗАПОЛНЕН"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {measurements.length > 10 && (
                <div
                  style={{
                    textAlign: "center",
                    fontSize: "12px",
                    color: "#888",
                    marginTop: "6px",
                  }}
                >
                  + еще {measurements.length - 10} записей
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Настройки автомобиля */}
      <details style={{ marginTop: "12px" }}>
        <summary
          style={{
            cursor: "pointer",
            color: "#666",
            fontSize: "13px",
            padding: "4px 0",
          }}
        >
          ⚙️ Настройки автомобиля
        </summary>
        <div
          style={{
            marginTop: "8px",
            padding: "12px 16px",
            backgroundColor: "white",
            borderRadius: "4px",
          }}
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(3, 1fr)",
              gap: "12px",
            }}
          >
            <div>
              <label
                style={{
                  fontSize: "12px",
                  color: "#666",
                  display: "block",
                  marginBottom: "4px",
                }}
              >
                📏 Длина кузова (м)
              </label>
              <input
                type="number"
                step="0.5"
                value={vehicleParams.length_m}
                onChange={(e) =>
                  setVehicleParams({
                    ...vehicleParams,
                    length_m: parseFloat(e.target.value),
                  })
                }
                style={{
                  width: "100%",
                  padding: "4px 8px",
                  fontSize: "14px",
                  border: "1px solid #ddd",
                  borderRadius: "4px",
                }}
              />
            </div>
            <div>
              <label
                style={{
                  fontSize: "12px",
                  color: "#666",
                  display: "block",
                  marginBottom: "4px",
                }}
              >
                📐 Ширина кузова (м)
              </label>
              <input
                type="number"
                step="0.1"
                value={vehicleParams.width_m}
                onChange={(e) =>
                  setVehicleParams({
                    ...vehicleParams,
                    width_m: parseFloat(e.target.value),
                  })
                }
                style={{
                  width: "100%",
                  padding: "4px 8px",
                  fontSize: "14px",
                  border: "1px solid #ddd",
                  borderRadius: "4px",
                }}
              />
            </div>
            <div>
              <label
                style={{
                  fontSize: "12px",
                  color: "#666",
                  display: "block",
                  marginBottom: "4px",
                }}
              >
                ⚫ Плотность угля (кг/м³)
              </label>
              <input
                type="number"
                step="10"
                value={vehicleParams.coal_density_kg_m3}
                onChange={(e) =>
                  setVehicleParams({
                    ...vehicleParams,
                    coal_density_kg_m3: parseFloat(e.target.value),
                  })
                }
                style={{
                  width: "100%",
                  padding: "4px 8px",
                  fontSize: "14px",
                  border: "1px solid #ddd",
                  borderRadius: "4px",
                }}
              />
            </div>
          </div>
          <div style={{ fontSize: "11px", color: "#999", marginTop: "8px" }}>
            💡 Укажите реальные размеры кузова для точного расчёта
          </div>
        </div>
      </details>
    </div>
  );
};

export default LidarViewer;
