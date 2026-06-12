// frontend/src/services/api.ts
import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000/api';

const api = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

export const weighingApi = {
    getCurrentWeight: () => api.get('/weighing/current'),
    getTrips: () => api.get('/weighing/trips'),
    startTrip: () => api.post('/weighing/start-trip'),
    endTrip: (tripId: number) => api.post(`/weighing/end-trip/${tripId}`),
};

export const lidarApi = {
    getScan: () => api.get('/lidar/scan'),
    getStatus: () => api.get('/lidar/status'),
    measure: (data: { truck_length_m: number; truck_width_m: number; coal_density_kg_m3: number }) => 
        api.post('/lidar/measure', data),
    getMeasurements: (limit: number = 50) => api.get(`/lidar/measurements?limit=${limit}`),
    getMeasurement: (id: number) => api.get(`/lidar/measurements/${id}`)
};

export const scan3dApi = {
    start: (scanId: string, length_m: number, width_m: number) => 
        api.post('/scan3d/start', { scan_id: scanId, truck_length_m: length_m, truck_width_m: width_m }),
    addProfile: (scanId: string, distances_mm: number[], position_m: number) => 
        api.post('/scan3d/add-profile', { scan_id: scanId, distances_mm, position_m }),
    stop: (scanId: string) => 
        api.post(`/scan3d/stop?scan_id=${scanId}`),  // ← ИСПРАВЛЕНО: query параметр
    getStatus: (scanId: string) => 
        api.get(`/scan3d/status/${scanId}`),
    getProfiles: (scanId: string, limit?: number) => 
        api.get(`/scan3d/profiles/${scanId}?limit=${limit || 100}`)
};

export default api;
