// frontend/src/components/Weighing/CurrentWeight.tsx
import React, { useEffect, useState } from 'react';
import { weighingApi } from '../../services/api';

interface WeightData {
    plate_number: string;
    weight: number;
    weight_type: string;
    is_stable: boolean;
    state: string;
}

export const CurrentWeight: React.FC = () => {
    const [data, setData] = useState<WeightData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchData = async () => {
            try {
                setError(null);
                const response = await weighingApi.getCurrentWeight();
                setData(response.data);
            } catch (error: any) {
                console.error('Error fetching weight:', error);
                setError(error.message || 'Ошибка загрузки данных');
            } finally {
                setLoading(false);
            }
        };

        fetchData();
        const interval = setInterval(fetchData, 2000);
        return () => clearInterval(interval);
    }, []);

    if (loading) return <div style={{ padding: 20 }}>Загрузка...</div>;
    
    if (error) return <div style={{ padding: 20, color: 'red' }}>Ошибка: {error}</div>;

    return (
        <div style={{ 
            background: 'white', 
            borderRadius: 10, 
            boxShadow: '0 4px 6px rgba(0,0,0,0.1)', 
            padding: 30,
            maxWidth: 500,
            margin: '0 auto'
        }}>
            <h2 style={{ marginTop: 0, color: '#333' }}>Текущее взвешивание</h2>
            <div style={{ 
                fontSize: 48, 
                fontWeight: 'bold', 
                margin: '20px 0', 
                padding: 20, 
                background: '#f5f5f5', 
                borderRadius: 5 
            }}>
                <span style={{ color: '#2c3e50' }}>{data?.weight || 0}</span>
                <span style={{ fontSize: 24, marginLeft: 10, color: '#7f8c8d' }}>kg</span>
            </div>
            <div style={{ textAlign: 'left', background: '#f9f9f9', padding: 15, borderRadius: 5 }}>
                <p><strong>Номер ТС:</strong> {data?.plate_number || '—'}</p>
                <p><strong>Тип взвешивания:</strong> {data?.weight_type || '—'}</p>
                <p><strong>Статус:</strong> {data?.state || '—'}</p>
                <p><strong>Стабильность:</strong> {data?.is_stable ? '✅ Да' : '❌ Нет'}</p>
            </div>
        </div>
    );
};