import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { labApi } from "../api";
import { ErrorBanner, Loading } from "../components/Ui";
import type { CoalFraction, CoalGrade, ExperimentPayload, MeasurementInput, Supplier, VolumeUnit } from "../types";

type DraftMeasurement = MeasurementInput & { id?: number };
const nowLocal = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 16); };
const blank = (): DraftMeasurement => ({ sequence_number: 1, entered_volume_value: 10, entered_volume_unit: "LITER", material_mass_kg: 0, is_included: true, exclusion_reason: null });
const density = (m: DraftMeasurement) => { const volume = m.entered_volume_unit === "LITER" ? m.entered_volume_value / 1000 : m.entered_volume_value; return volume > 0 && m.material_mass_kg > 0 ? m.material_mass_kg / volume : null; };

export function ExperimentFormPage() {
  const { id } = useParams(); const editId = id ? Number(id) : null; const navigate = useNavigate();
  const [directories, setDirectories] = useState<{ grades: CoalGrade[]; fractions: CoalFraction[]; suppliers: Supplier[] }>({ grades: [], fractions: [], suppliers: [] });
  const [form, setForm] = useState({ experiment_number: "", coal_grade_id: 0, coal_fraction_id: 0, supplier_id: 0, batch_number: "", invoice_number: "", sampled_at: "", tested_at: nowLocal(), moisture_percent: "", laboratory_user_name: "", comment: "" });
  const [measurements, setMeasurements] = useState<DraftMeasurement[]>([blank()]); const [deleted, setDeleted] = useState<number[]>([]);
  const [loading, setLoading] = useState(Boolean(editId)); const [saving, setSaving] = useState(false); const [dirty, setDirty] = useState(false); const [status, setStatus] = useState("DRAFT"); const [error, setError] = useState<string | null>(null);

  useEffect(() => { Promise.all([labApi.grades(), labApi.fractions(), labApi.suppliers()]).then(([grades, fractions, suppliers]) => setDirectories({ grades, fractions, suppliers })).catch((e) => setError(e.message)); }, []);
  useEffect(() => { if (!editId) return; labApi.experiment(editId).then((x) => { setStatus(x.status); setForm({ experiment_number: x.experiment_number, coal_grade_id: x.coal_grade_id, coal_fraction_id: x.coal_fraction_id, supplier_id: x.supplier_id, batch_number: x.batch_number || "", invoice_number: x.invoice_number || "", sampled_at: x.sampled_at ? x.sampled_at.slice(0, 16) : "", tested_at: x.tested_at.slice(0, 16), moisture_percent: x.moisture_percent?.toString() || "", laboratory_user_name: x.laboratory_user_name, comment: x.comment || "" }); setMeasurements(x.measurements); }).catch((e) => setError(e.message)).finally(() => setLoading(false)); }, [editId]);
  useEffect(() => { const handler = (e: BeforeUnloadEvent) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } }; addEventListener("beforeunload", handler); return () => removeEventListener("beforeunload", handler); }, [dirty]);
  const updateForm = (key: keyof typeof form, value: string | number) => { setForm((x) => ({ ...x, [key]: value })); setDirty(true); };
  const updateMeasurement = (index: number, patch: Partial<DraftMeasurement>) => { setMeasurements((rows) => rows.map((row, i) => i === index ? { ...row, ...patch } : row)); setDirty(true); };
  const included = measurements.map(density).filter((value, index): value is number => value !== null && measurements[index].is_included);
  const average = included.length ? included.reduce((a, b) => a + b, 0) / included.length : null;
  const remove = (index: number) => { const row = measurements[index]; if (row.id) setDeleted((x) => [...x, row.id!]); setMeasurements((x) => x.filter((_, i) => i !== index)); setDirty(true); };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setError(null);
    if (status !== "DRAFT") return setError("Редактировать можно только черновик.");
    if (!form.coal_grade_id || !form.coal_fraction_id || !form.supplier_id) return setError("Заполните марку, фракцию и поставщика.");
    if (measurements.some((m) => m.entered_volume_value <= 0 || m.material_mass_kg <= 0)) return setError("Масса и объём должны быть больше нуля.");
    if (measurements.some((m) => !m.is_included && !m.exclusion_reason?.trim())) return setError("Укажите причину исключения измерения.");
    setSaving(true);
    const payload: ExperimentPayload = { ...form, batch_number: form.batch_number || null, invoice_number: form.invoice_number || null, sampled_at: form.sampled_at ? new Date(form.sampled_at).toISOString() : null, tested_at: new Date(form.tested_at).toISOString(), moisture_percent: form.moisture_percent === "" ? null : Number(form.moisture_percent), comment: form.comment || null, measurements: measurements.map(({ id: _id, ...row }) => row) };
    try {
      if (!editId) { const created = await labApi.createExperiment(payload); setDirty(false); navigate(`/experiments/${created.id}`); }
      else {
        const { experiment_number: _number, measurements: _rows, ...main } = payload; await labApi.updateExperiment(editId, main);
        for (const measurementId of deleted) await labApi.deleteMeasurement(measurementId);
        for (const row of measurements) { const { id: measurementId, ...body } = row; if (measurementId) await labApi.updateMeasurement(measurementId, body); else await labApi.addMeasurement(editId, body); }
        setDirty(false); navigate(`/experiments/${editId}`);
      }
    } catch (e) { setError((e as Error).message); } finally { setSaving(false); }
  };

  if (loading) return <Loading />;
  const readonly = status !== "DRAFT";
  return <form onSubmit={submit}>
    <div className="page-heading"><div><p className="eyebrow">{editId ? "Редактирование" : "Новое исследование"}</p><h1>{editId ? form.experiment_number : "Создание исследования"}</h1><p>Исходные данные и параллельные измерения плотности.</p></div><div className="heading-actions"><Link className="button secondary" to={editId ? `/experiments/${editId}` : "/experiments"} onClick={(e) => { if (dirty && !confirm("Есть несохранённые изменения. Покинуть страницу?")) e.preventDefault(); }}>Отмена</Link><button className="button primary" disabled={saving || readonly}>{saving ? "Сохранение…" : "Сохранить"}</button></div></div>
    <ErrorBanner message={error} />{readonly && <div className="alert">Исследование завершено или архивировано и доступно только для просмотра.</div>}
    <section className="panel form-section"><div className="panel-title"><div><h2>Основные сведения</h2><span>Поля, идентифицирующие пробу</span></div></div><div className="form-grid">
      <label><span>Номер исследования *</span><input required disabled={Boolean(editId) || readonly} value={form.experiment_number} onChange={(e) => updateForm("experiment_number", e.target.value)} /></label>
      <label><span>Марка угля *</span><select required disabled={readonly} value={form.coal_grade_id || ""} onChange={(e) => updateForm("coal_grade_id", Number(e.target.value))}><option value="">Выберите</option>{directories.grades.map((x) => <option key={x.id} value={x.id}>{x.code} · {x.name}</option>)}</select></label>
      <label><span>Фракция *</span><select required disabled={readonly} value={form.coal_fraction_id || ""} onChange={(e) => updateForm("coal_fraction_id", Number(e.target.value))}><option value="">Выберите</option>{directories.fractions.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
      <label><span>Поставщик *</span><select required disabled={readonly} value={form.supplier_id || ""} onChange={(e) => updateForm("supplier_id", Number(e.target.value))}><option value="">Выберите</option>{directories.suppliers.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
      <label><span>Номер партии</span><input disabled={readonly} value={form.batch_number} onChange={(e) => updateForm("batch_number", e.target.value)} /></label><label><span>Номер накладной</span><input disabled={readonly} value={form.invoice_number} onChange={(e) => updateForm("invoice_number", e.target.value)} /></label>
      <label><span>Отбор пробы</span><input type="datetime-local" disabled={readonly} value={form.sampled_at} onChange={(e) => updateForm("sampled_at", e.target.value)} /></label><label><span>Дата анализа *</span><input required type="datetime-local" disabled={readonly} value={form.tested_at} onChange={(e) => updateForm("tested_at", e.target.value)} /></label>
      <label><span>Лаборант *</span><input required disabled={readonly} value={form.laboratory_user_name} onChange={(e) => updateForm("laboratory_user_name", e.target.value)} /></label><label><span>Рабочая влажность, %</span><input type="number" min="0" max="100" step="0.001" disabled={readonly} value={form.moisture_percent} onChange={(e) => updateForm("moisture_percent", e.target.value)} /></label>
      <label className="span-2"><span>Комментарий</span><textarea rows={3} disabled={readonly} value={form.comment} onChange={(e) => updateForm("comment", e.target.value)} /></label>
    </div></section>
    <section className="panel form-section"><div className="panel-title"><div><h2>Измерения</h2><span>Backend повторно проверит все расчёты</span></div><button type="button" className="button secondary small" disabled={readonly} onClick={() => { setMeasurements((x) => [...x, { ...blank(), sequence_number: x.length + 1 }]); setDirty(true); }}>Добавить измерение</button></div>
      <div className="table-scroll"><table className="measurement-table"><thead><tr><th>№</th><th>Объём</th><th>Единица</th><th>Масса, кг</th><th>Плотность</th><th>В среднем</th><th>Причина исключения</th><th /></tr></thead><tbody>{measurements.map((m, index) => <tr key={m.id || `new-${index}`}><td><input aria-label="Номер измерения" type="number" min="1" disabled={readonly} value={m.sequence_number} onChange={(e) => updateMeasurement(index, { sequence_number: Number(e.target.value) })} /></td><td><input aria-label="Объём сосуда" type="number" min="0.000001" step="any" disabled={readonly} value={m.entered_volume_value} onChange={(e) => updateMeasurement(index, { entered_volume_value: Number(e.target.value) })} /></td><td><select aria-label="Единица объёма" disabled={readonly} value={m.entered_volume_unit} onChange={(e) => updateMeasurement(index, { entered_volume_unit: e.target.value as VolumeUnit })}><option value="LITER">л</option><option value="M3">м³</option></select></td><td><input aria-label="Масса угля" type="number" min="0.000001" step="any" disabled={readonly} value={m.material_mass_kg} onChange={(e) => updateMeasurement(index, { material_mass_kg: Number(e.target.value) })} /></td><td><strong>{density(m)?.toFixed(2) || "—"}</strong><small>кг/м³</small></td><td><input aria-label="Включено в среднее" className="checkbox" type="checkbox" disabled={readonly} checked={m.is_included} onChange={(e) => updateMeasurement(index, { is_included: e.target.checked, exclusion_reason: e.target.checked ? null : m.exclusion_reason })} /></td><td><input aria-label="Причина исключения" disabled={readonly || m.is_included} required={!m.is_included} value={m.exclusion_reason || ""} onChange={(e) => updateMeasurement(index, { exclusion_reason: e.target.value })} placeholder={m.is_included ? "Не требуется" : "Обязательно"} /></td><td><button type="button" className="danger-link" disabled={readonly} onClick={() => remove(index)}>Удалить</button></td></tr>)}</tbody></table></div>
      <div className="summary-strip"><div><span>Включено измерений</span><strong>{included.length}</strong></div><div><span>Предварительная средняя плотность</span><strong>{average == null ? "—" : `${average.toFixed(2)} кг/м³`}</strong></div></div>
    </section>
  </form>;
}
