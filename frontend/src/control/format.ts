export const scaleLabels: Record<string, string> = {
  Empty: "Весы свободны", LoadScale: "Автомобиль заезжает", Weighing: "Взвешивание",
  ReadyWeighing: "Вес готов", WeighingComplete: "Взвешивание завершено", UnLoadScale: "Автомобиль съезжает",
};
export const lidarLabels: Record<string, string> = { RECORDING: "Идёт запись лидара", COMPLETED: "Лидарный проход сохранён", FAILED: "Ошибка записи" };
export const volumeLabels: Record<string, string> = { NOT_CALCULATED: "Не рассчитан", CALCULATING: "Выполняется расчёт", CALCULATED: "Рассчитан", FAILED: "Ошибка расчёта", INSUFFICIENT_DATA: "Недостаточно данных" };
export const kg = (value: number | null | undefined) => value == null ? "—" : `${new Intl.NumberFormat("ru-RU").format(value)} кг`;
export const dateTime = (value: string | null | undefined) => value ? new Date(value).toLocaleString("ru-RU") : "—";
