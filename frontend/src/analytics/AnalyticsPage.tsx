import {FormEvent,useEffect,useState} from "react";
import "./analytics.css";

type Supplier={id:number;name:string};
type Row={supplier_id:number;supplier_name:string;trip_count:number;total_weight_t:string;total_volume_m3:null;bulk_density_t_m3:null};
type Report={rows:Row[];totals:{trip_count:number;total_weight_t:string;total_volume_m3:null;bulk_density_t_m3:null}};
const today=()=>new Date().toISOString().slice(0,10);
const monthStart=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-01`};

export function AnalyticsPage(){
 const defaults={date_from:monthStart(),date_to:today(),supplier_id:""};
 const [draft,setDraft]=useState(defaults),[filters,setFilters]=useState(defaults),[suppliers,setSuppliers]=useState<Supplier[]>([]),[report,setReport]=useState<Report|null>(null),[loading,setLoading]=useState(false),[error,setError]=useState("");
 const query=(f=filters)=>{const q=new URLSearchParams({date_from:f.date_from,date_to:f.date_to});if(f.supplier_id)q.set("supplier_id",f.supplier_id);return q};
 const load=async()=>{setLoading(true);setError("");try{const [r,s]=await Promise.all([fetch(`/api/analytics/supplier-summary?${query()}`),fetch("/api/admin/suppliers?page_size=100")]);if(!r.ok)throw new Error("Не удалось сформировать отчёт");setReport(await r.json());if(s.ok)setSuppliers((await s.json()).items)}catch(e){setError(e instanceof Error?e.message:"Ошибка отчёта")}finally{setLoading(false)}};
 useEffect(()=>{load()},[filters]);
 const apply=(e:FormEvent)=>{e.preventDefault();if(draft.date_from>draft.date_to){setError("Дата начала не может быть позже даты окончания");return}setFilters({...draft})};
 const reset=()=>{const value={date_from:monthStart(),date_to:today(),supplier_id:""};setDraft(value);setFilters(value)};
 const exportExcel=()=>{window.open(`/api/analytics/supplier-summary/export?${query()}`,"_self")};
 return <main className="analytics-page"><h1>Аналитика</h1><div className="analytics-tabs"><button className="active">Сводка по поставщикам</button></div>
  <form className="analytics-filters" onSubmit={apply}><label>Дата с<input type="date" value={draft.date_from} onChange={e=>setDraft({...draft,date_from:e.target.value})}/></label><label>Дата по<input type="date" value={draft.date_to} onChange={e=>setDraft({...draft,date_to:e.target.value})}/></label><label>Поставщик<select value={draft.supplier_id} onChange={e=>setDraft({...draft,supplier_id:e.target.value})}><option value="">Все поставщики</option>{suppliers.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label><button className="primary-action">Применить</button><button type="button" onClick={reset}>Сбросить</button><button type="button" onClick={exportExcel}>Выгрузить Excel</button></form>
  {error&&<div className="analytics-error">{error}</div>}{loading?<p>Формирование отчёта…</p>:report&&!report.rows.length?<p className="analytics-empty">За выбранный период данные отсутствуют</p>:report&&<div className="analytics-table"><table><thead><tr><th>Поставщик</th><th>Рейсов</th><th>Вес, т</th><th>Объем, м³</th><th>Насыпная плотность, т/м³</th></tr></thead><tbody>{report.rows.map(x=><tr key={x.supplier_id}><td>{x.supplier_name}</td><td>{x.trip_count}</td><td>{x.total_weight_t}</td><td>—</td><td>—</td></tr>)}</tbody><tfoot><tr><th>ИТОГО</th><th>{report.totals.trip_count}</th><th>{report.totals.total_weight_t}</th><th>—</th><th>—</th></tr></tfoot></table></div>}
 </main>
}
