# Camera + LiDAR diagnostic recording

Инфраструктура записи готова. Нужен реальный controlled pass. Recorder не классифицирует движение, не рассчитывает объём и не меняет production FSM.

## Включение и выключение

По умолчанию запись полностью выключена. Для одного исследовательского запуска задайте в окружении backend:

```env
CAMERA_LIDAR_DIAGNOSTIC_RECORDING=true
DIAGNOSTIC_DATA_DIR=C:\weight-control-data\diagnostics
DIAGNOSTIC_MAX_DURATION_SEC=900
DIAGNOSTIC_QUEUE_SIZE=500
DIAGNOSTIC_MAX_BYTES=2147483648
```

Перезапустите backend. Для выключения установите `CAMERA_LIDAR_DIAGNOSTIC_RECORDING=false` и снова перезапустите. При `false` каталоги и файлы не создаются.

## Что и когда записывается

Запись начинается при открытии существующей `LidarPassSession` на `LoadScale` и завершается ровно там, где её сейчас завершает coordinator. Это специально позволяет увидеть фактическое production-поведение при остановке. Trip ID может быть привязан позднее: manifest обновляется, событие `TRIP_BOUND` попадает в timeline.

Camera recorder — listener единственного существующего `CameraClient`. Он не подключается к камере, не создаёт второй client/capture thread и получает каждый опубликованный JPEG непосредственно из producer. Frames сохраняются отдельно: это больше файлов, зато нет ложного предположения constant FPS и каждый frame однозначно связан с собственным timestamp.

LiDAR polling и пауза 300 мс не изменены. Каждый `DIST1` сохраняется lossless: полный `ranges_raw`, позиционный `ranges_mm` с `null` для invalid beam, `valid_mask`, start/end angle, angular step, beam count и raw scale/offset. Derived 70°/100…3000 мм representation лежит отдельно в `filtered`.

Частоты из переменной части `LMDscandata` пока намеренно не декодируются по абсолютным позициям: первый реальный тест доказал, что такой offset ненадёжен (`native_scan_frequency_hz=0`, `measurement_frequency_hz=50`). По протоколу SICK scan frequency — частота scans/rotations, а measurement frequency — частота отдельных measurement shots; это разные величины. Диагностический формат сохраняет `telegram_header_tokens` lossless, выставляет обе частоты в `null` и пишет `frequency_parse_status`. Достоверную scan frequency следует позже читать protocol-aware parser либо отдельной командой scan configuration; значение 50 не подставляется как native scan frequency.

## Структура

```text
data/diagnostics/<session_key>/
  manifest.json
  events.jsonl
  markers.jsonl
  lidar/raw_scans.jsonl
  camera/frames.csv
  camera/frame_00000001.jpg
  analysis/
    summary.json
    lidar_profiles.csv
    camera_frames.csv
    events.csv
    matches.csv
```

Единый event contract:

```json
{
  "type": "event",
  "event": "SCALE_SNAPSHOT",
  "captured_utc": "...",
  "captured_monotonic_ns": 123,
  "payload": {"scale_state": "Weighing", "weight_kg": 1000, "stable": true}
}
```

Markers используют ту же envelope-структуру с `type=marker`, `event=OPERATOR_MARKER` и label внутри `payload`.

Все samples содержат UTC и monotonic time одного backend process. LiDAR дополнительно содержит request start, response receive, processing completion и acquisition latency. Camera содержит publication sequence и processing completion. Сопоставление выполняется по ближайшему monotonic timestamp, не по sequence.

Тяжёлая запись выполняется background writer через bounded queue. Acquisition только делает `put_nowait`. При queue/duration/size limit production продолжает работу, manifest становится `PARTIAL`, а `dropped_record_count` увеличивается.

## Ручные markers

Только при активной opt-in записи:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/camera/debug/diagnostics/marker -ContentType application/json -Body '{"label":"STOPPED"}'
```

Допустимы `MOVING`, `STOPPED`, `RESUMED`. Endpoint не меняет FSM — только пишет timestamped marker.

## Controlled tests

Перед каждым тестом убедитесь, что backend запущен с opt-in config, часы сервера корректны, камера и LiDAR имеют connected status, а на диске достаточно места.

- TEST A: поставить marker `MOVING`, провести машину без остановки, дождаться штатного завершения.
- TEST B: marker `MOVING`, пройти около 2/3 кузова, остановиться на 10–20 с и поставить `STOPPED`, продолжить с `RESUMED`.
- TEST C: выполнить несколько коротких stop/start и на каждом переходе ставить соответствующий marker.

Не запускайте следующий проход, пока в предыдущем manifest не появился конечный status.

## Analyzer

На сервере из каталога `backend`:

```powershell
..\venv_weight\Scripts\python.exe scripts\analyze_camera_lidar_session.py data\diagnostics\<session_key>
```

Analyzer выдаёт фактические LiDAR Hz/latency, camera FPS/interval jitter, события и nearest Camera↔LiDAR delta. Он не выполняет optical flow: реальных camera recordings в рабочей копии пока нет, поэтому эксперимент LK будет обоснован только после получения TEST A/B/C.

После теста нужно передать весь каталог `<session_key>` без изменений, backend logs на интервал теста, фактический сценарий/погоду/освещение и измеренную длину кузова. Если manifest `PARTIAL`, обязательно передать его: причина лимита, drops и errors являются частью результата.
