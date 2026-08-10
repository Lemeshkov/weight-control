# TEST B: offline CameraMotionEstimator

## Статус анализа

Реальная сессия `9fafd185315e4b8194d7b59b5afb6f39` находится на production/test server в `C:\weight-control-data\diagnostics`, но отсутствует в локальной рабочей среде Codex. Поэтому manual timestamps, detection delays, distributions, число LiDAR profiles во время STOP и итог `YES / CONDITIONALLY / NO` здесь намеренно не указаны. Synthetic tests подтверждают только helper mathematics.

Production CameraClient, coordinator, LiDAR acquisition, API, БД, frontend и volume не изменялись.

## Запуск full-frame baseline

На сервере из `backend`:

```powershell
..\venv_weight\Scripts\python.exe scripts\analyze_camera_motion.py `
  C:\weight-control-data\diagnostics\9fafd185315e4b8194d7b59b5afb6f39
```

Выходной каталог `motion_analysis` содержит:

- `motion_summary.json`;
- `camera_motion.csv`;
- `lidar_motion.csv`;
- `fusion_motion.csv`;
- `motion_plot.png`.

Analyzer проверяет два operator markers, порядок camera timestamps, наличие всех JPEG и SHA-256, затем выполняет CLAHE + sparse Lucas–Kanade, forward/backward validation, MAD outlier rejection, dominant-axis projection и experimental hysteresis. Farneback запускается как comparator; для быстрого прогона его можно отключить `--skip-farneback`.

LiDAR сравнивается только по одинаковым beam indexes: common valid mask, median absolute difference, RMSE и correlation. Fusion использует простые deterministic rules; к production она не подключена.

## ROI

Full-frame результат — baseline, не финальная конфигурация. Выбрать representative JPEG и сохранить normalized polygon:

```powershell
..\venv_weight\Scripts\python.exe scripts\select_camera_roi.py `
  C:\weight-control-data\diagnostics\9fafd185315e4b8194d7b59b5afb6f39\camera\frame_00000100.jpg `
  C:\weight-control-data\diagnostics\9fafd185315e4b8194d7b59b5afb6f39\camera_roi.json
```

Левой кнопкой отметить минимум три точки, Enter сохранить, R сбросить, Esc отменить. Повторный анализ:

```powershell
..\venv_weight\Scripts\python.exe scripts\analyze_camera_motion.py `
  C:\weight-control-data\diagnostics\9fafd185315e4b8194d7b59b5afb6f39 `
  --roi C:\weight-control-data\diagnostics\9fafd185315e4b8194d7b59b5afb6f39\camera_roi.json `
  --output-dir C:\weight-control-data\diagnostics\9fafd185315e4b8194d7b59b5afb6f39\motion_analysis_roi
```

## Что читать в результате

`motion_summary.json` содержит manual STOP/RESUME monotonic timestamps и длительность, candidate thresholds, dominant axis, detected transitions/delays, false STOP/MOVING duration, UNKNOWN duration, moving/stopped distributions камеры и LiDAR, число profiles before/during/after STOP и CPU/distributions LK/Farneback.

Около 4 fps достаточно только если LK сохраняет достаточное число tracks и нет больших inter-frame displacements. Если valid tracks систематически проваливаются именно на MOVING, следующий эксперимент должен записать 10–20 fps либо запускать estimator на internal CameraClient stream; это нельзя заключить без CSV реального прогона.

Разница `events_count=67` против `manifest.record_counts.events=65` не является ошибкой recorder: базовый analyzer объединяет 65 строк `events.jsonl` и 2 строки `markers.jsonl` в общий timeline. Manifest правильно считает их раздельно.

## Будущая slice policy

- `MOVING`: разрешать новый spatial slice.
- `STOPPED`: raw scan сохранять, longitudinal position не увеличивать, spatial slice не добавлять.
- `RESUMED`: продолжать ту же reconstruction.

Это только проектирование. Переход к production `MotionProvider` возможен лишь после просмотра реальных delays, false intervals и conflicts в результатах TEST B. ЭТАП 4 — согласование thresholds/ROI и feature-flagged shadow MotionProvider без влияния на production decisions; метрический `ΔY` остаётся отдельным экспериментом.
