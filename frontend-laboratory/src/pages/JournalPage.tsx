import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { labApi } from "../api";
import { EmptyState, ErrorBanner, formatDate, formatDensity, Loading, StatusBadge } from "../components/Ui";
import type { CoalGrade, ExperimentFilters, ExperimentListResponse, Supplier } from "../types";

const initialFilters: ExperimentFilters = { limit: 10, offset: 0, status: "" };

export function JournalPage() {
  const [filters, setFilters] = useState(initialFilters);
  const [data, setData] = useState<ExperimentListResponse | null>(null);
  const [grades, setGrades] = useState<CoalGrade[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => { setLoading(true); setError(null); labApi.experiments(filters).then(setData).catch((e) => setError(e.message)).finally(() => setLoading(false)); };
  useEffect(load, [filters]);
  useEffect(() => { Promise.all([labApi.grades(), labApi.suppliers()]).then(([g, s]) => { setGrades(g); setSuppliers(s); }).catch(() => undefined); }, []);
  const update = (key: keyof ExperimentFilters, value: string | number) => setFilters((old) => ({ ...old, [key]: value, offset: 0 }));
  const page = Math.floor(filters.offset / filters.limit) + 1;
  const pages = Math.max(1, Math.ceil((data?.total || 0) / filters.limit));

  return <>
    <div className="page-heading"><div><p className="eyebrow">Исследования</p><h1>Журнал лаборатории</h1><p>Результаты определения насыпной плотности и рабочей влажности.</p></div>
      <div className="heading-actions"><a className="button secondary" href={labApi.exportUrl()}>Экспорт CSV</a><Link className="button primary" to="/experiments/new">Создать исследование</Link></div></div>
    <section className="panel filters">
      <label className="search-field"><span>Поиск</span><input value={filters.search || ""} onChange={(e) => update("search", e.target.value)} placeholder="Номер, партия или накладная" /></label>
      <label><span>Дата от</span><input type="date" value={filters.date_from || ""} onChange={(e) => update("date_from", e.target.value)} /></label>
      <label><span>Дата до</span><input type="date" value={filters.date_to || ""} onChange={(e) => update("date_to", e.target.value)} /></label>
      <label><span>Марка</span><select value={filters.coal_grade_id || ""} onChange={(e) => update("coal_grade_id", Number(e.target.value) || "")}><option value="">Все</option>{grades.map((x) => <option key={x.id} value={x.id}>{x.code} · {x.name}</option>)}</select></label>
      <label><span>Поставщик</span><select value={filters.supplier_id || ""} onChange={(e) => update("supplier_id", Number(e.target.value) || "")}><option value="">Все</option>{suppliers.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
      <label><span>Статус</span><select value={filters.status || ""} onChange={(e) => update("status", e.target.value)}><option value="">Все</option><option value="DRAFT">Черновик</option><option value="COMPLETED">Завершено</option><option value="ARCHIVED">Архив</option></select></label>
    </section>
    <ErrorBanner message={error} />
    <section className="panel table-panel">
      <div className="panel-title"><div><h2>Исследования</h2><span>{data?.total || 0} записей</span></div><button className="text-button" onClick={() => setFilters(initialFilters)}>Сбросить фильтры</button></div>
      {loading ? <Loading /> : !data?.items.length ? <EmptyState title="Исследований не найдено" text="Измените фильтры или создайте первое исследование." /> :
      <div className="table-scroll"><table><thead><tr><th>Исследование</th><th>Даты</th><th>Материал</th><th>Поставка</th><th>Измерения</th><th>Показатели</th><th>Статус</th><th /></tr></thead><tbody>
        {data.items.map((item) => <tr key={item.id}><td><strong>{item.experiment_number}</strong><small>{item.laboratory_user_name}</small></td><td>{formatDate(item.tested_at, true)}<small>Отбор: {formatDate(item.sampled_at, true)}</small></td><td>{item.coal_grade}<small>{item.coal_fraction}</small></td><td>{item.supplier}<small>{item.batch_number || "Без партии"} · {item.invoice_number || "Без накладной"}</small></td><td>{item.measurements_count}</td><td><strong>{formatDensity(item.average_density_kg_m3)}</strong><small>Влажность: {item.moisture_percent == null ? "—" : `${item.moisture_percent}%`}</small></td><td><StatusBadge status={item.status} /></td><td><Link className="row-link" to={`/experiments/${item.id}`}>Открыть</Link></td></tr>)}
      </tbody></table></div>}
      <div className="pagination"><span>Страница {page} из {pages}</span><div><button disabled={filters.offset === 0} onClick={() => setFilters((x) => ({ ...x, offset: Math.max(0, x.offset - x.limit) }))}>Назад</button><button disabled={page >= pages} onClick={() => setFilters((x) => ({ ...x, offset: x.offset + x.limit }))}>Далее</button></div></div>
    </section>
  </>;
}
