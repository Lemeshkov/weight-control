import type { ExperimentStatus } from "../types";

export const formatDate = (value?: string | null, withTime = false) => value ? new Intl.DateTimeFormat("ru-RU", { dateStyle: "short", ...(withTime ? { timeStyle: "short" } : {}) }).format(new Date(value)) : "—";
export const formatDensity = (value?: number | null) => value == null ? "—" : `${Number(value).toFixed(2)} кг/м³`;
export const statusLabels: Record<ExperimentStatus, string> = { DRAFT: "Черновик", COMPLETED: "Завершено", ARCHIVED: "Архив" };
export function StatusBadge({ status }: { status: ExperimentStatus }) { return <span className={`status status-${status.toLowerCase()}`}>{statusLabels[status]}</span>; }
export function EmptyState({ title, text }: { title: string; text: string }) { return <div className="empty"><strong>{title}</strong><p>{text}</p></div>; }
export function ErrorBanner({ message }: { message: string | null }) { return message ? <div className="alert alert-error">{message}</div> : null; }
export function Loading() { return <div className="loading"><span />Загрузка данных…</div>; }
