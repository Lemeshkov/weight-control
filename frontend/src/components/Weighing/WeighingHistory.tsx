
// // frontend/src/components/WeighingHistory.tsx
// import React, { useEffect, useState } from 'react';
// import axios from 'axios';

// interface Trip {
//     id: number;
//     plate_number: string;
//     entry_time: string;
//     exit_time: string | null;
//     status: string;
//     weight_brutto: number | null;
//     weight_tare: number | null;
//     net_weight: number | null;
// }

// // Группированная запись (по номеру ТС)
// interface GroupedTrip {
//     plate_number: string;
//     first_entry_time: string;
//     last_exit_time: string | null;
//     total_weight_brutto: number;
//     total_weight_tare: number;
//     total_net_weight: number;
//     trips_count: number;
//     is_active: boolean;
//     trip_ids: number[];
// }

// export const WeighingHistory: React.FC = () => {
//     const [trips, setTrips] = useState<Trip[]>([]);
//     const [groupedTrips, setGroupedTrips] = useState<GroupedTrip[]>([]);
//     const [loading, setLoading] = useState(true);
//     const [error, setError] = useState<string | null>(null);
//     const [groupByPlate, setGroupByPlate] = useState(true); // Переключатель группировки

//     const fetchTrips = async () => {
//         try {
//             setError(null);
//             const response = await axios.get('http://localhost:8000/api/weighing/trips');
//             console.log('📊 Получены рейсы:', response.data);
//             setTrips(response.data);
            
//             // Группируем по номеру ТС
//             const grouped = groupTripsByPlate(response.data);
//             setGroupedTrips(grouped);
//         } catch (error: any) {
//             console.error('Error fetching trips:', error);
//             setError(error.message || 'Ошибка загрузки истории');
//         } finally {
//             setLoading(false);
//         }
//     };

//     // Функция группировки рейсов по номеру ТС
//     const groupTripsByPlate = (trips: Trip[]): GroupedTrip[] => {
//         const map = new Map<string, GroupedTrip>();
        
//         trips.forEach(trip => {
//             const plate = trip.plate_number;
            
//             if (!map.has(plate)) {
//                 map.set(plate, {
//                     plate_number: plate,
//                     first_entry_time: trip.entry_time,
//                     last_exit_time: trip.exit_time,
//                     total_weight_brutto: trip.weight_brutto || 0,
//                     total_weight_tare: trip.weight_tare || 0,
//                     total_net_weight: trip.net_weight || 0,
//                     trips_count: 1,
//                     is_active: trip.status !== 'completed',
//                     trip_ids: [trip.id]
//                 });
//             } else {
//                 const existing = map.get(plate)!;
                
//                 // Обновляем время первого въезда (самый ранний)
//                 if (trip.entry_time < existing.first_entry_time) {
//                     existing.first_entry_time = trip.entry_time;
//                 }
                
//                 // Обновляем время последнего выезда (самый поздний)
//                 if (trip.exit_time && (!existing.last_exit_time || trip.exit_time > existing.last_exit_time)) {
//                     existing.last_exit_time = trip.exit_time;
//                 }
                
//                 // Суммируем веса
//                 existing.total_weight_brutto += (trip.weight_brutto || 0);
//                 existing.total_weight_tare += (trip.weight_tare || 0);
//                 existing.total_net_weight += (trip.net_weight || 0);
//                 existing.trips_count += 1;
//                 existing.trip_ids.push(trip.id);
                
//                 // Если хоть один рейс активен - считаем активным
//                 if (trip.status !== 'completed') {
//                     existing.is_active = true;
//                 }
//             }
//         });
        
//         // Сортируем по времени въезда (сначала новые)
//         return Array.from(map.values()).sort((a, b) => 
//             b.first_entry_time.localeCompare(a.first_entry_time)
//         );
//     };

//     useEffect(() => {
//         fetchTrips();
//         const interval = setInterval(fetchTrips, 10000);
//         return () => clearInterval(interval);
//     }, []);

//     if (loading) {
//         return (
//             <div style={{ 
//                 background: 'white', 
//                 borderRadius: 10, 
//                 padding: 20, 
//                 marginTop: 20,
//                 textAlign: 'center',
//                 color: '#666',
//                 boxShadow: '0 4px 6px rgba(0,0,0,0.1)'
//             }}>
//                 ⏳ Загрузка истории...
//             </div>
//         );
//     }

//     return (
//         <div style={{ 
//             background: 'white', 
//             borderRadius: 10, 
//             boxShadow: '0 4px 6px rgba(0,0,0,0.1)', 
//             padding: 20,
//             marginTop: 20
//         }}>
//             <h3 style={{ marginTop: 0, color: '#333', display: 'flex', alignItems: 'center', gap: 15, flexWrap: 'wrap' }}>
//                 <span>📋 История взвешиваний</span>
//                 <span style={{ fontSize: 14, fontWeight: 'normal', color: '#666' }}>
//                     {groupByPlate ? `${groupedTrips.length} автомобилей` : `${trips.length} записей`}
//                 </span>
//                 <button
//                     onClick={() => setGroupByPlate(!groupByPlate)}
//                     style={{
//                         padding: '4px 12px',
//                         fontSize: 12,
//                         backgroundColor: groupByPlate ? '#17a2b8' : '#6c757d',
//                         color: 'white',
//                         border: 'none',
//                         borderRadius: 4,
//                         cursor: 'pointer'
//                     }}
//                 >
//                     {groupByPlate ? '📦 Группировать' : '📋 Все записи'}
//                 </button>
//                 <button
//                     onClick={fetchTrips}
//                     style={{
//                         padding: '4px 12px',
//                         fontSize: 12,
//                         backgroundColor: '#007bff',
//                         color: 'white',
//                         border: 'none',
//                         borderRadius: 4,
//                         cursor: 'pointer'
//                     }}
//                 >
//                     🔄 Обновить
//                 </button>
//             </h3>
            
//             {error && (
//                 <div style={{ 
//                     color: '#721c24', 
//                     background: '#f8d7da', 
//                     padding: 10, 
//                     borderRadius: 5,
//                     marginBottom: 10
//                 }}>
//                     ❌ {error}
//                 </div>
//             )}

//             {/* ГРУППИРОВАННАЯ ТАБЛИЦА (ПО УМОЛЧАНИЮ) */}
//             {groupByPlate ? (
//                 groupedTrips.length === 0 ? (
//                     <div style={{ textAlign: 'center', padding: 30, color: '#999' }}>
//                         Нет записей о взвешиваниях
//                     </div>
//                 ) : (
//                     <div style={{ overflowX: 'auto' }}>
//                         <table style={{ 
//                             width: '100%', 
//                             borderCollapse: 'collapse',
//                             fontSize: 14
//                         }}>
//                             <thead>
//                                 <tr style={{ background: '#f0f0f0' }}>
//                                     <th style={{ padding: 10, border: '1px solid #ddd', textAlign: 'left' }}>Номер ТС</th>
//                                     <th style={{ padding: 10, border: '1px solid #ddd', textAlign: 'left' }}>Первый въезд</th>
//                                     <th style={{ padding: 10, border: '1px solid #ddd', textAlign: 'left' }}>Последний выезд</th>
//                                     <th style={{ padding: 10, border: '1px solid #ddd', textAlign: 'left' }}>Статус</th>
//                                     <th style={{ padding: 10, border: '1px solid #ddd', textAlign: 'right' }}>Рейсов</th>
//                                     <th style={{ padding: 10, border: '1px solid #ddd', textAlign: 'right' }}>Всего Брутто (кг)</th>
//                                     <th style={{ padding: 10, border: '1px solid #ddd', textAlign: 'right' }}>Всего Тара (кг)</th>
//                                     <th style={{ padding: 10, border: '1px solid #ddd', textAlign: 'right' }}>Всего Нетто (кг)</th>
//                                 </tr>
//                             </thead>
//                             <tbody>
//                                 {groupedTrips.map((group) => (
//                                     <tr key={group.plate_number}>
//                                         <td style={{ padding: 8, border: '1px solid #ddd', fontWeight: 'bold' }}>
//                                             {group.plate_number}
//                                         </td>
//                                         <td style={{ padding: 8, border: '1px solid #ddd' }}>
//                                             {new Date(group.first_entry_time).toLocaleString()}
//                                         </td>
//                                         <td style={{ padding: 8, border: '1px solid #ddd' }}>
//                                             {group.last_exit_time ? new Date(group.last_exit_time).toLocaleString() : '—'}
//                                         </td>
//                                         <td style={{ padding: 8, border: '1px solid #ddd' }}>
//                                             <span style={{
//                                                 display: 'inline-block',
//                                                 padding: '3px 10px',
//                                                 borderRadius: 12,
//                                                 fontSize: 12,
//                                                 fontWeight: 'bold',
//                                                 background: group.is_active ? '#fff3cd' : '#d4edda',
//                                                 color: group.is_active ? '#856404' : '#155724'
//                                             }}>
//                                                 {group.is_active ? '⏳ Активен' : '✅ Завершен'}
//                                             </span>
//                                         </td>
//                                         <td style={{ padding: 8, border: '1px solid #ddd', textAlign: 'center' }}>
//                                             {group.trips_count}
//                                         </td>
//                                         <td style={{ padding: 8, border: '1px solid #ddd', textAlign: 'right' }}>
//                                             {group.total_weight_brutto.toLocaleString()}
//                                         </td>
//                                         <td style={{ padding: 8, border: '1px solid #ddd', textAlign: 'right' }}>
//                                             {group.total_weight_tare.toLocaleString()}
//                                         </td>
//                                         <td style={{ 
//                                             padding: 8, 
//                                             border: '1px solid #ddd', 
//                                             textAlign: 'right',
//                                             fontWeight: 'bold',
//                                             color: group.total_net_weight > 0 ? '#28a745' : '#dc3545'
//                                         }}>
//                                             {group.total_net_weight.toLocaleString()}
//                                         </td>
//                                     </tr>
//                                 ))}
//                             </tbody>
//                         </table>
//                     </div>
//                 )
//             ) : (
//                 /* ДЕТАЛЬНАЯ ТАБЛИЦА (все записи) */
//                 trips.length === 0 ? (
//                     <div style={{ textAlign: 'center', padding: 30, color: '#999' }}>
//                         Нет записей о взвешиваниях
//                     </div>
//                 ) : (
//                     <div style={{ overflowX: 'auto' }}>
//                         <table style={{ 
//                             width: '100%', 
//                             borderCollapse: 'collapse',
//                             fontSize: 14
//                         }}>
//                             <thead>
//                                 <tr style={{ background: '#f0f0f0' }}>
//                                     <th style={{ padding: 10, border: '1px solid #ddd', textAlign: 'left' }}>ID</th>
//                                     <th style={{ padding: 10, border: '1px solid #ddd', textAlign: 'left' }}>Номер ТС</th>
//                                     <th style={{ padding: 10, border: '1px solid #ddd', textAlign: 'left' }}>Въезд</th>
//                                     <th style={{ padding: 10, border: '1px solid #ddd', textAlign: 'left' }}>Выезд</th>
//                                     <th style={{ padding: 10, border: '1px solid #ddd', textAlign: 'left' }}>Статус</th>
//                                     <th style={{ padding: 10, border: '1px solid #ddd', textAlign: 'right' }}>Брутто (кг)</th>
//                                     <th style={{ padding: 10, border: '1px solid #ddd', textAlign: 'right' }}>Тара (кг)</th>
//                                     <th style={{ padding: 10, border: '1px solid #ddd', textAlign: 'right' }}>Нетто (кг)</th>
//                                 </tr>
//                             </thead>
//                             <tbody>
//                                 {trips.map((trip) => (
//                                     <tr key={trip.id}>
//                                         <td style={{ padding: 8, border: '1px solid #ddd', textAlign: 'center' }}>
//                                             {trip.id}
//                                         </td>
//                                         <td style={{ padding: 8, border: '1px solid #ddd', fontWeight: 'bold' }}>
//                                             {trip.plate_number}
//                                         </td>
//                                         <td style={{ padding: 8, border: '1px solid #ddd' }}>
//                                             {new Date(trip.entry_time).toLocaleString()}
//                                         </td>
//                                         <td style={{ padding: 8, border: '1px solid #ddd' }}>
//                                             {trip.exit_time ? new Date(trip.exit_time).toLocaleString() : '—'}
//                                         </td>
//                                         <td style={{ padding: 8, border: '1px solid #ddd' }}>
//                                             <span style={{
//                                                 display: 'inline-block',
//                                                 padding: '3px 10px',
//                                                 borderRadius: 12,
//                                                 fontSize: 12,
//                                                 fontWeight: 'bold',
//                                                 background: trip.status === 'completed' ? '#d4edda' : '#fff3cd',
//                                                 color: trip.status === 'completed' ? '#155724' : '#856404'
//                                             }}>
//                                                 {trip.status === 'completed' ? '✅ Завершен' : '⏳ Активен'}
//                                             </span>
//                                         </td>
//                                         <td style={{ padding: 8, border: '1px solid #ddd', textAlign: 'right' }}>
//                                             {trip.weight_brutto?.toLocaleString() || '—'}
//                                         </td>
//                                         <td style={{ padding: 8, border: '1px solid #ddd', textAlign: 'right' }}>
//                                             {trip.weight_tare?.toLocaleString() || '—'}
//                                         </td>
//                                         <td style={{ 
//                                             padding: 8, 
//                                             border: '1px solid #ddd', 
//                                             textAlign: 'right',
//                                             fontWeight: 'bold',
//                                             color: trip.net_weight && trip.net_weight > 0 ? '#28a745' : '#dc3545'
//                                         }}>
//                                             {trip.net_weight?.toLocaleString() || '—'}
//                                         </td>
//                                     </tr>
//                                 ))}
//                             </tbody>
//                         </table>
//                     </div>
//                 )
//             )}
//         </div>
//     );
// };
// frontend/src/components/WeighingHistory.tsx
import React, { useEffect, useState } from 'react';
import axios from 'axios';

interface Trip {
    id: number;
    plate_number: string;
    entry_time: string;
    exit_time: string | null;
    status: string;
    weight_brutto: number | null;
    weight_tare: number | null;
    net_weight: number | null;
}

export const WeighingHistory: React.FC = () => {
    const [trips, setTrips] = useState<Trip[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const fetchTrips = async () => {
        try {
            setError(null);
            const response = await axios.get('http://localhost:8000/api/weighing/trips');
            console.log('📊 Получены рейсы:', response.data);
            setTrips(response.data);
        } catch (error: any) {
            console.error('Error fetching trips:', error);
            setError(error.message || 'Ошибка загрузки истории');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchTrips();
        const interval = setInterval(fetchTrips, 10000);
        return () => clearInterval(interval);
    }, []);

    if (loading) {
        return (
            <div style={{ 
                background: 'white', 
                borderRadius: 10, 
                padding: 20, 
                marginTop: 20,
                textAlign: 'center',
                color: '#666',
                boxShadow: '0 4px 6px rgba(0,0,0,0.1)'
            }}>
                ⏳ Загрузка истории...
            </div>
        );
    }

    return (
        <div style={{ 
            background: 'white', 
            borderRadius: 10, 
            boxShadow: '0 4px 6px rgba(0,0,0,0.1)', 
            padding: 20,
            marginTop: 20
        }}>
            <h3 style={{ marginTop: 0, color: '#333', display: 'flex', alignItems: 'center', gap: 15, flexWrap: 'wrap' }}>
                <span>📋 История взвешиваний</span>
                <span style={{ fontSize: 14, fontWeight: 'normal', color: '#666' }}>
                    {trips.length} записей
                </span>
                <button
                    onClick={fetchTrips}
                    style={{
                        padding: '4px 12px',
                        fontSize: 12,
                        backgroundColor: '#007bff',
                        color: 'white',
                        border: 'none',
                        borderRadius: 4,
                        cursor: 'pointer'
                    }}
                >
                    🔄 Обновить
                </button>
                <button
                    onClick={async () => {
                        try {
                            const response = await axios.post('http://localhost:8000/api/weighing/journal/sync?days=7');
                            alert(`✅ Синхронизировано ${response.data.synced} записей`);
                            fetchTrips();
                        } catch (error: any) {
                            alert(`❌ Ошибка: ${error.message}`);
                        }
                    }}
                    style={{
                        padding: '4px 12px',
                        fontSize: 12,
                        backgroundColor: '#17a2b8',
                        color: 'white',
                        border: 'none',
                        borderRadius: 4,
                        cursor: 'pointer'
                    }}
                >
                    🔄 Синхронизировать
                </button>
            </h3>
            
            {error && (
                <div style={{ 
                    color: '#721c24', 
                    background: '#f8d7da', 
                    padding: 10, 
                    borderRadius: 5,
                    marginBottom: 10
                }}>
                    ❌ {error}
                </div>
            )}

            {trips.length === 0 ? (
                <div style={{ textAlign: 'center', padding: 30, color: '#999' }}>
                    Нет записей о взвешиваниях
                </div>
            ) : (
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ 
                        width: '100%', 
                        borderCollapse: 'collapse',
                        fontSize: 14
                    }}>
                        <thead>
                            <tr style={{ background: '#f0f0f0' }}>
                                <th style={{ padding: 10, border: '1px solid #ddd', textAlign: 'left' }}>ID</th>
                                <th style={{ padding: 10, border: '1px solid #ddd', textAlign: 'left' }}>Номер ТС</th>
                                <th style={{ padding: 10, border: '1px solid #ddd', textAlign: 'left' }}>Въезд</th>
                                <th style={{ padding: 10, border: '1px solid #ddd', textAlign: 'left' }}>Выезд</th>
                                <th style={{ padding: 10, border: '1px solid #ddd', textAlign: 'left' }}>Статус</th>
                                <th style={{ padding: 10, border: '1px solid #ddd', textAlign: 'right' }}>Брутто (кг)</th>
                                <th style={{ padding: 10, border: '1px solid #ddd', textAlign: 'right' }}>Тара (кг)</th>
                                <th style={{ padding: 10, border: '1px solid #ddd', textAlign: 'right' }}>Нетто (кг)</th>
                            </tr>
                        </thead>
                        <tbody>
                            {trips.map((trip) => (
                                <tr key={trip.id}>
                                    <td style={{ padding: 8, border: '1px solid #ddd', textAlign: 'center' }}>
                                        {trip.id}
                                    </td>
                                    <td style={{ padding: 8, border: '1px solid #ddd', fontWeight: 'bold' }}>
                                        {trip.plate_number}
                                    </td>
                                    <td style={{ padding: 8, border: '1px solid #ddd' }}>
                                        {trip.entry_time ? new Date(trip.entry_time).toLocaleString() : '—'}
                                    </td>
                                    <td style={{ padding: 8, border: '1px solid #ddd' }}>
                                        {trip.exit_time ? new Date(trip.exit_time).toLocaleString() : '—'}
                                    </td>
                                    <td style={{ padding: 8, border: '1px solid #ddd' }}>
                                        <span style={{
                                            display: 'inline-block',
                                            padding: '3px 10px',
                                            borderRadius: 12,
                                            fontSize: 12,
                                            fontWeight: 'bold',
                                            background: trip.status === 'completed' ? '#d4edda' : '#fff3cd',
                                            color: trip.status === 'completed' ? '#155724' : '#856404'
                                        }}>
                                            {trip.status === 'completed' ? '✅ Завершен' : '⏳ Активен'}
                                        </span>
                                    </td>
                                    <td style={{ padding: 8, border: '1px solid #ddd', textAlign: 'right' }}>
                                        {trip.weight_brutto?.toLocaleString() || '—'}
                                    </td>
                                    <td style={{ padding: 8, border: '1px solid #ddd', textAlign: 'right' }}>
                                        {trip.weight_tare?.toLocaleString() || '—'}
                                    </td>
                                    <td style={{ 
                                        padding: 8, 
                                        border: '1px solid #ddd', 
                                        textAlign: 'right',
                                        fontWeight: 'bold',
                                        color: trip.net_weight && trip.net_weight > 0 ? '#28a745' : '#dc3545'
                                    }}>
                                        {trip.net_weight?.toLocaleString() || '—'}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
};