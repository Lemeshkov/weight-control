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
    getStatus: () => api.get('/lidar/status'), // Добавляем получение статуса
};

export default api;