# TEST B: offline CameraMotionEstimator

Анализ выполнен на реальной локальной сессии
`diagnostics/9fafd185315e4b8194d7b59b5afb6f39`. Production CameraClient,
RTSP/MJPEG, coordinator, LiDAR acquisition, API, БД, frontend и volume не менялись.

## Входные данные

- `manifest.json`: `COMPLETED`, 173 camera frames, 123 LiDAR profiles, 2 markers;
- `camera/frames.csv` и 173 JPEG с проверенными предыдущим анализом SHA-256;
- `lidar/raw_scans.jsonl`;
- `markers.jsonl`: STOPPED `866736218000000`, RESUMED `866752875000000`;
- `camera_roi.json`: существующий polygon кузова;
- `motion_analysis/camera_motion.csv` и `motion_analysis_roi/camera_motion.csv`.

Ручной STOP длился 16.657 s. Перебор выполняется по quantile-derived порогам,
stop confirmation 250–2000 ms и resume confirmation 0–1000 ms. Objective сильнее
штрафует false STOP, но также требует оба реальных перехода и штрафует false MOVING,
UNKNOWN и лишние transitions. Это предотвращает тривиальные always-moving/always-stopped
решения. Всего сравниваются 17 220 конфигураций для LK/Farneback, full-frame/ROI.

## Результат

Лучший Farneback full-frame и ROI дали одинаковый state timeline:

- stop threshold: `1.361371e-05` (full), `1.445997e-07` (ROI);
- start threshold: `0.00887307` (full), `0.0754444` (ROI);
- stop/resume confirmation: 2000/750 ms;
- STOP delay: 1875 ms; RESUME delay: 15 ms;
- false STOP: 15 ms; false MOVING: 1875 ms; UNKNOWN: 0 ms;
- два перехода, false transitions: 0; correct time fraction: 95.63%.

LK full оставил 4109 ms false STOP. LK ROI снизил false STOP до 15 ms, но получил
4860 ms STOP delay, 1108 ms UNKNOWN и пять наблюдаемых переходов (часть из UNKNOWN).
Следовательно ROI полезен для sparse LK, но сам по себе не решает его нестабильность.
Исходный false STOP около 9562 ms был следствием слишком высокого автоматически
выбранного stop threshold и короткого hysteresis, а не отсутствия движения камеры.

LiDAR median absolute profile difference равен 2 mm и в MOVING, и в STOPPED
(p90: 3 и 2 mm). Даже лучший одиночный threshold имеет ограниченную balanced accuracy;
он не является независимым подтверждением движения на этом проезде. Fusion разумно
оставить будущим дополнительным сигналом, но не использовать здесь как veto/источник
истины.

При camera-only policy из 123 профилей: 81 slice принят, 42 подавлены; один профиль
ошибочно подавлен при MOVING, шесть приняты в первые 1.875 s реального STOP. Raw profiles
при этом должны сохраняться всегда.

Около 4 fps достаточно для обнаружения этого длинного STOP и быстрого RESUME, но
квантование кадрами плюс 2 s подтверждение задаёт задержку STOP. Одного проезда
недостаточно для production MotionProvider: нужны независимые проезды с иной скоростью,
светом, кузовом и длительностью остановки.

## Запуск

Из `backend`:

```powershell
..\venv_weight\Scripts\python.exe scripts\tune_camera_motion.py `
  ..\diagnostics\9fafd185315e4b8194d7b59b5afb6f39
```

Результаты записываются в `motion_tuning/tuning_summary.json`,
`threshold_candidates.csv` и `profile_acceptance.csv`.

Вывод: **CONDITIONALLY**. Камера пригодна как кандидат MotionProvider в shadow mode,
если Farneback работает по фиксированной ROI/full-frame конфигурации с duration-based
hysteresis, raw LiDAR не теряется во время STOP, а следующий реальный тест подтверждает
ограничения задержки и отсутствие false STOP на нескольких условиях съёмки.
