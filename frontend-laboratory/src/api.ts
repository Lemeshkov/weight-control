import axios, { AxiosError } from "axios";
import type { AuditEntry, CoalFraction, CoalGrade, Experiment, ExperimentFilters, ExperimentListResponse, ExperimentPayload, Measurement, MeasurementInput, Supplier } from "./types";

const baseURL = (import.meta.env.VITE_LAB_API_URL as string | undefined)?.replace(/\/$/, "") || "http://localhost:8001";

const client = axios.create({ baseURL, headers: { "Content-Type": "application/json" }, timeout: 15000 });

export class ApiError extends Error {
  constructor(message: string, public status?: number) { super(message); }
}
client.interceptors.response.use((response) => response, (error: AxiosError<{ detail?: string | Array<{ msg: string }> }>) => {
  const detail = error.response?.data?.detail;
  const message = Array.isArray(detail) ? detail.map((item) => item.msg).join("; ") : detail || error.message || "Ошибка запроса";
  return Promise.reject(new ApiError(message, error.response?.status));
});

const params = (values: ExperimentFilters) => Object.fromEntries(Object.entries(values)
  .filter(([, value]) => value !== "" && value !== undefined)
  .map(([key, value]) => [key, key === "date_to" && typeof value === "string" ? `${value}T23:59:59` : value]));

export const labApi = {
  health: () => client.get<{ status: string; service: string }>("/api/health").then((r) => r.data),
  grades: () => client.get<CoalGrade[]>("/api/v1/laboratory/coal-grades").then((r) => r.data),
  createGrade: (data: { code: string; name: string; description?: string }) => client.post<CoalGrade>("/api/v1/laboratory/coal-grades", data).then((r) => r.data),
  fractions: () => client.get<CoalFraction[]>("/api/v1/laboratory/coal-fractions").then((r) => r.data),
  createFraction: (data: { name: string; min_size_mm?: number; max_size_mm?: number }) => client.post<CoalFraction>("/api/v1/laboratory/coal-fractions", data).then((r) => r.data),
  suppliers: () => client.get<Supplier[]>("/api/v1/laboratory/suppliers").then((r) => r.data),
  createSupplier: (data: { code?: string; name: string }) => client.post<Supplier>("/api/v1/laboratory/suppliers", data).then((r) => r.data),
  experiments: (filters: ExperimentFilters) => client.get<ExperimentListResponse>("/api/v1/laboratory/experiments", { params: params(filters) }).then((r) => r.data),
  experiment: (id: number) => client.get<Experiment>(`/api/v1/laboratory/experiments/${id}`).then((r) => r.data),
  createExperiment: (data: ExperimentPayload) => client.post<Experiment>("/api/v1/laboratory/experiments", data).then((r) => r.data),
  updateExperiment: (id: number, data: Partial<Omit<ExperimentPayload, "experiment_number" | "measurements">>) => client.patch<Experiment>(`/api/v1/laboratory/experiments/${id}`, data).then((r) => r.data),
  addMeasurement: (id: number, data: MeasurementInput) => client.post<Measurement>(`/api/v1/laboratory/experiments/${id}/measurements`, data).then((r) => r.data),
  updateMeasurement: (id: number, data: Partial<MeasurementInput>) => client.patch<Measurement>(`/api/v1/laboratory/measurements/${id}`, data).then((r) => r.data),
  deleteMeasurement: (id: number) => client.delete(`/api/v1/laboratory/measurements/${id}`),
  complete: (id: number) => client.post<Experiment>(`/api/v1/laboratory/experiments/${id}/complete`).then((r) => r.data),
  archive: (id: number) => client.post<Experiment>(`/api/v1/laboratory/experiments/${id}/archive`).then((r) => r.data),
  audit: (id: number) => client.get<AuditEntry[]>(`/api/v1/laboratory/experiments/${id}/audit-log`).then((r) => r.data),
  exportUrl: () => `${baseURL}/api/v1/laboratory/experiments/export`,
};
