import { Fragment, useState } from "react";
import { dateTime, kg, lidarLabels, volumeLabels } from "./format";
import type { ControlHistoryItem } from "./types";

function Details({ item }: { item: ControlHistoryItem }) {
  const lidar = item.lidar;
  return <div className="trip-details">
    <section><h4>Весовой блок</h4><p>Trip: №{item.trip_id}</p><p>Заезд: {dateTime(item.entry_time)}</p><p>Стабильный вес: {kg(lidar?.stable_weight_kg)}</p><p>Максимальная масса: {kg(lidar?.maximum_observed_weight_kg)}</p>{lidar?.error_message === "stable_weight_missing" && <p className="warning-text">Нет подтверждённого стабильного веса</p>}</section>
    <section><h4>Лидарный блок</h4>{lidar ? <><p>Сессия: {lidar.session_key || `№${lidar.session_id} (ключ не сохранялся)`}</p><p>Статус: {lidarLabels[lidar.status] || lidar.status}</p><p>Начало: {dateTime(lidar.started_at)}</p><p>LoadScale: {dateTime(lidar.load_scale_at)}</p><p>Завершение: {dateTime(lidar.ended_at)}</p><p>Профили: {lidar.profiles_count}, до триггера: {lidar.pre_trigger_profiles_count}</p><p>Валидные профили: {lidar.valid_profiles_count}</p><p>Точки: {lidar.points_valid} из {lidar.points_total}</p><p>JSON: {lidar.data_file_path || "Не создан"}</p><p>Объём: {volumeLabels[lidar.volume_status] || lidar.volume_status}</p></> : <p>Лидарная сессия отсутствует</p>}</section>
    <section><h4>Накладная</h4><p>{item.acceptance_status === "COMPLETED" ? "Оформлена" : item.acceptance_status === "DRAFT" ? "Черновик" : "Ожидает"}</p></section>
    <section><h4>Камера</h4><p>{item.photo_path ? `Фото: ${item.photo_path}` : "Фото проезда не сохранялось"}</p></section>
  </div>;
}

export function RecentTripsTable({ items, error, refresh, page, totalPages, total, onPageChange }: { items: ControlHistoryItem[]; error: string | null; refresh: () => void; page: number; totalPages: number; total: number; onPageChange: (page: number) => void }) {
  const [expanded, setExpanded] = useState<number | null>(null);
  return <section className="history-card"><div className="section-heading"><div><span className="eyebrow">Журнал</span><h2>Последние рейсы</h2></div><button onClick={refresh}>Обновить</button></div>
    {error && <div className="notice notice--warn">{error}. Уже загруженные строки сохранены.</div>}
    {!items.length ? <div className="empty-state">Сохранённых рейсов пока нет</div> : <div className="table-wrap"><table><thead><tr><th>Время</th><th>Автомобиль</th><th>Госномер</th><th>Вес</th><th>Профили</th><th>Лидар</th><th>Объём</th><th>Действия</th></tr></thead><tbody>{items.map(item => <Fragment key={item.trip_id}><tr><td>{dateTime(item.entry_time)}</td><td>{item.vehicle.brand || "—"}</td><td><b>{item.vehicle.license_plate}</b></td><td>{kg(item.weight.value_kg)}</td><td>{item.lidar?.profiles_count ?? "—"}</td><td>{item.lidar ? lidarLabels[item.lidar.status] || item.lidar.status : "Нет сессии"}</td><td>{item.lidar ? volumeLabels[item.lidar.volume_status] || item.lidar.volume_status : "—"}</td><td><button aria-expanded={expanded === item.trip_id} onClick={() => setExpanded(expanded === item.trip_id ? null : item.trip_id)}>Подробнее</button></td></tr>{expanded === item.trip_id && <tr><td colSpan={8}><Details item={item} /></td></tr>}</Fragment>)}</tbody></table></div>}
    {totalPages > 0 && <div className="history-pagination"><button disabled={page <= 1} onClick={() => onPageChange(page - 1)}>Назад</button><span>Страница {page} из {totalPages} · всего {total}</span><button disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>Вперёд</button></div>}
  </section>;
}
