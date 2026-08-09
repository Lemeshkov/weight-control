# Camera + LiDAR: исследовательский отчёт перед 3D-реконструкцией

Дата аудита: 2026-08-09. Это проектирование и offline-диагностика. Production lifecycle, API, БД, миграции, логика веса и объёма не изменялись.

## 1. CameraClient сейчас

`CameraClient` создаётся один раз в `routers/camera.py`. Один background thread получает HTTP snapshot, декодирует его OpenCV, уменьшает ширину до 1024 px при необходимости, кодирует JPEG quality 70 и под lock заменяет единственный latest frame. `/frame` и `/stream` читают этот cache; MJPEG consumer опрашивает его каждые 200 мс. Это уже правильная основа «один producer — несколько consumers», но истории кадров/subscription API нет.

Timestamp — naive `datetime.now()` хоста после HTTP/decode/encode, не timestamp сенсора. Пауза 200 мс после успешного snapshot задаёт верхнюю границу около 5 fps плюс network/decode latency. Значит, фактические fps и jitter нужно измерять, а не считать равными 5.

## 2. LiDAR acquisition сейчас

Один `LidarProfileBuffer` непрерывно вызывает `LidarClient.get_scan_data()`. Каждый scan запрашивается синхронной CoLa-командой `sRN LMDscandata`; перед `recv` есть фиксированные 300 мс. На успешной итерации дополнительной паузы нет. Поэтому приложение получает не более примерно 3,33 profile/s плюс socket/parse/scheduling latency. Это polling, не native streaming.

LMS511 аппаратно поддерживает несколько scan frequencies, но текущий код не читает/сохраняет фактическую конфигурацию частоты. Её нельзя вывести из модели прибора или `profiles_count`; для следующего теста надо один раз прочитать scan configuration/telegram metadata и сохранить её вместе с проходом. Спецификация LMS511 перечисляет 25/35/50/75/100 Hz, но это возможности устройства, не доказательство текущей настройки.

## 3. Что означает `profiles_count=25`

Это ровно `len(session.profiles)`: 25 отдельных успешных итераций чтения/парсинга LiDAR, то есть 25 последовательных 2D scans/cross-sections. Sampling или ограничение «25» отсутствует.

`pre_trigger_profiles_count=15` означает 15 профилей из rolling buffer до перехода весов в `LoadScale`. При окне 5 с и polling около 3,3 Hz число 15 правдоподобно, но без JSON это только объяснение механизма, не измерение конкретного прохода.

## 4. Структура одного profile

Сохраняются: aware UTC `captured_at` после получения/парсинга, process-local `sequence_number`, число исходных ranges `points_total`, число оставшихся значений `points_valid`, массив `distances_mm`, min/max/average.

До сохранения применяется центральное окно 70° (`keep=int(total*70/190)`, затем нечётная ширина) и range filter 100…3000 мм. Критический дефект формата для будущей 3D-задачи: удаляются invalid ranges вместе с их beam indexes, а start angle/angular step/scale/offset не сохраняются. Поэтому точные угол, Cartesian `(x,z)` и даже point-to-point comparison по одному и тому же лучу из текущего JSON восстановить нельзя.

## 5. Реальная статистика сохранённого прохода

В рабочей копии отсутствует каталог `backend/data/lidar_passes/`, файлы `lidar_pass_*.json` и записи камеры. Вхождения 25/15 в tests — fixtures, не реальные измерения. Поэтому duration, интервалы, points per profile, similarity и stationary segments конкретного прохода не вычислялись и не выдумывались.

Добавлен offline-анализатор `backend/scripts/analyze_lidar_pass.py`. После помещения реального файла команда

```powershell
python scripts/analyze_lidar_pass.py data/lidar_passes/lidar_pass_....json
```

создаст `summary.json` и `profiles.csv` с timeline, delta time, effective frequency, counts, min/max, MAD/RMSE/correlation соседних profiles. Нормализованная интерполяция массивов разной длины полезна только как диагностическая signature; она не восстанавливает потерянные beam indexes.

## 6. Частота и интервалы

Теоретический предел текущего приложения — около 3,33 Hz из-за `sleep(0.3)`. Реальные интервалы определяются по `captured_at`; аппаратная scan frequency отдельно неизвестна. Camera — не более около 5 fps. В обоих потоках timestamps поставлены после I/O/обработки, поэтому включают различную latency.

## 7. Почему профилей только 25 и возможны ли потери

Rolling buffer ограничен 5 сек и 1000 элементами, но после открытия session новые profiles копируются в неограниченный session list. `max_count=1000` не ограничивает итоговый pass. Coordinator синхронизирует buffer примерно каждые 500 мс; при ~3,3 Hz и окне 5 с обычно успевает забрать всё, однако process stalls дольше 5 с приведут к потере profiles. 25, вероятнее всего, отражает короткий lifecycle примерно 7–8 секунд с pre-trigger, но точная длительность требует JSON.

## 8. Синхронизация Camera/LiDAR

Текущие timestamps несовместимы для точного matching: camera — naive local wall clock, LiDAR — aware UTC wall clock; оба после разной обработки, monotonic time отсутствует. На этапе 2 каждый producer должен добавлять `captured_utc`, `captured_monotonic_ns`, sequence и acquisition latency. `CameraMotionSample` хранится в bounded time-indexed ring buffer; LiDAR profile получает ближайший sample по monotonic timestamp в пределах configurable tolerance. По порядковым номерам связывать нельзя.

## 9. CameraMotionEstimator

Предлагаемый первый кандидат: grayscale ROI → `goodFeaturesToTrack` → pyramidal Lucas–Kanade → forward/backward check → rejection плохих tracks → robust aggregation. DTO: timestamp, state, confidence, tracked/valid count, median flow vector, projected motion, p75/p90 magnitude, diagnostic quality flags.

## 10. Lucas–Kanade против Farneback

Sparse LK предпочтителен: дешевле, даёт отдельные tracks и понятную confidence/filtering, хорошо соответствует 5 fps и фиксированной ROI. Farneback полезен как offline comparator/fallback для малоугловатой поверхности, но тяжелее, сильнее реагирует на фон, снег, дым и освещение. Ни один вариант нельзя признать рабочим без реального видео.

## 11. ROI strategy

ROI должна быть нормализованным polygon/mask в config с optional exclusion polygons. Настройка — calibration screen поверх live frame: оператор отмечает коридор кузова и исключает фон/людей/механизмы. Координаты алгоритма не hardcode. Отдельная статичная background ROI полезна для оценки вибрации камеры и вычитания global motion.

## 12. Motion score

После quality и forward/backward filtering проектировать известную ось движения `u`: `signed_flow=dot(flow,u)`, отдельно считать orthogonal residual. Основные robust features: valid ratio, median signed flow, median absolute projected flow, p75/p90 magnitude, directional-consistency ratio. Confidence должна падать при малом числе features, высоком residual и разнонаправленном потоке. Mean не использовать как главный score.

## 13. FSM MOVING/STOPPED

`UNKNOWN → MOVING → STOP_CANDIDATE → STOPPED → MOVE_CANDIDATE → MOVING`. Нужны разные configurable `motion_stop_threshold` и `motion_start_threshold`, `stop_confirm_ms`, `move_confirm_ms`, minimum features и timeout в UNKNOWN. Порогов сейчас назначать нельзя.

## 14. Hysteresis

STOP подтверждается только непрерывным low-score окном; движение — отдельным более высоким threshold и своим окном. Плохой frame не равен STOP: он даёт UNKNOWN и не должен накапливать stop confirmation. Решение привязывать к elapsed monotonic time, не к количеству кадров.

## 15. Остановка 2–3 минуты

В желаемой архитектуре reader продолжает принимать raw profiles, longitudinal position остаётся неизменной, session остаётся той же. Но текущий production coordinator завершает session после трёх stable `Weighing` samples и ещё 1 с либо сразу на `ReadyWeighing/WeighingComplete`. Следовательно, требуемый lifecycle STOP/RESUME сейчас не реализован и конфликтует с текущим завершением; на этом этапе он намеренно не менялся.

## 16. Как не создавать duplicate spatial slices

Разделить diagnostic acquisitions и spatial slices. В STOPPED хранить агрегат интервала (start/end, raw count, similarity distribution, representative first/median/last) и, лишь в opt-in debug recording, все compressed raw scans. Новый spatial slice принимать только при надёжном MOVING и накопленном `Δy` больше spatial step. При текущем polling за 3 минуты придёт около 600, а не «тысячи», profiles; при переходе к native rate их действительно будут тысячи.

## 17. Может ли камера дать `Δy` в метрах

Из pixel optical flow сама по себе — нет: perspective, depth, truck geometry и feature location меняют масштаб. Камера надёжнее подходит для MOVING/STOPPED и относительного displacement. Метрическая `Δy` возможна только после calibration и проверки на данных.

## 18. Calibration/homography

Нужны camera intrinsics/distortion, стабильный mounting, направление longitudinal axis и correspondences с известными наземными координатами. Homography метрична только для features на одной известной плоскости; борта/груз находятся на разных depth и нарушают модель. Контрольные метки/линия на ground plane предпочтительнее tracks по кузову. Известная длина кузова годится для post-hoc scale check, но не гарантирует локальную `Δy`.

## 19. Нужен ли encoder

Для достоверного объёма encoder/другой независимый longitudinal sensor остаётся рекомендуемым ground truth и потенциальным production provider. Камеру сначала стоит доказать как stop detector; метрический odometry — отдельный эксперимент. Интерфейс `MotionProvider` должен позволять Camera/LiDAR/Encoder без переписывания reconstruction.

## 20. LiDAR как второй motion signal

Сравнивать соседние profiles на общей фиксированной angular grid: valid mask/count, median absolute difference, RMSE, robust correlation и небольшой angular shift. Текущий JSON этого строго не позволяет из-за потерянных indexes. Даже правильная similarity неоднозначна: длинный однородный борт может почти не меняться при движении, поэтому это corroborating signal, не единственный источник.

## 21. Sensor fusion

Начать с deterministic rules: согласованные confident states усиливают confidence; один confident provider при UNKNOWN второго принимается с пониженной confidence; конфликт confident MOVING/STOPPED даёт UNKNOWN и diagnostic conflict; encoder, если появится и валиден, имеет приоритет для `Δy`. Kalman filter сейчас не нужен.

## 22. Роль Open3D

Open3D не установлен в текущем venv. Официальный `open3d 0.19.0` имеет CPython 3.11 Windows x86-64 wheel. Он уместен как optional offline dependency для PointCloud, voxel downsample, statistical/radius outlier removal, PLY/PCD, visualization и будущего mesh. Raw acquisition и longitudinal motion от него не зависят; ICP нельзя делать единственным odometry source.

## 23. Архитектура 2D→3D

`RawProfile(indexed ranges + geometry + timestamps) → calibrated ROI/filter → CrossSection(x,z,valid mask)`. Параллельно Camera → MotionEstimator и LiDAR similarity → MotionFusion. Только accepted motion increment создаёт `SpatialSlice(profile, y, points[x,y,z], source, confidence)`, последовательность образует `PassPointCloud`. Raw, filtered и reconstructed форматы должны быть versioned и раздельны.

## 24. Расчёт объёма через cross-sections

Предпочтительно считать cargo area `A_i` относительно empty-body baseline на каждом slice, затем trapezoidal integration `V_i=(A_i+A_(i+1))/2*Δy`. Это интерпретируемо и терпимее к sparse 2D data. Mesh volume оставить diagnostic: holes, occlusions, борта и неверный longitudinal scale могут дать внешне красивый, но неверный результат.

## 25. `vehicle_profiles`

Сервис содержит nominal length/width/height, один scalar `empty_height_mm` и допустимые point/spread ranges для типов машин. Это prior/catalog, не геометрия пустого кузова. Для area нужны versioned baseline cross-sections в той же calibration/angular grid: сначала type template, затем при необходимости индивидуальный кузов/прицеп. Cargo area — площадь между observed cargo surface и valid inner-body baseline с masks бортов/пустот.

## 26. Какие реальные данные ещё нужны

Нужны synchronized camera frame sequence/video + per-frame UTC/monotonic timestamps, полный indexed LiDAR range vector + start/step/count/scale/offset/native scan config, scale state, session key, Trip ID, operator-labeled movement/stop intervals, camera calibration/ROI и измеренная длина кузова. Желательны encoder/контрольные метки и empty-body проходы.

## 27. Controlled tests

Снять одним recorder: (1) проход без остановки; (2) проход, STOP 10–20 с, resume; (3) несколько коротких stop/start. Не ждать сразу 2–3 минуты. Для каждого синхронно сохранить все перечисленные данные и ручную разметку момента stop/start; повторить при дневном/ночном свете и плохой погоде.

## 28. Риски и критерии успеха

Риски: низкая текстура/блики/темнота, снег/дым/люди, вибрация, snapshot jitter, потерянная angular indexing, clock skew, преждевременное завершение coordinator, однородный LiDAR profile, homography violation и отсутствие baseline. Измерять stop/move latency, false STOP/MOVING time, valid tracking ratio, UNKNOWN share, agreement Camera/LiDAR, longitudinal length error, slice spacing error и repeatability. Нормативы выбрать только после labeled data.

## 29. План этапа 2

1. Сначала добавить opt-in dev recorder и versioned raw diagnostic format, не меняя lifecycle.
2. Записать/разметить controlled tests и прогнать offline LK/Farneback + LiDAR similarity.
3. Выбрать ROI, thresholds и hysteresis по данным; подтвердить camera stop detector.
4. Отдельно испытать метрическую calibration против известной длины/encoder.
5. После согласования внедрить `MotionProvider/Fusion`, STOP/RESUME lifecycle и spatial-slice decimation за feature flags.
6. Собрать empty-body baselines; только затем прототипировать cross-section volume и сравнивать с эталонными объёмами.

## Источники по оборудованию и библиотекам

- SICK LMS511 datasheet: https://www.sick.com/media/pdf/1/41/941/dataSheet_LMS511-10100-PRO_1046135_en.pdf
- OpenCV optical flow documentation: https://docs.opencv.org/4.x/d4/dee/tutorial_optical_flow.html
- Open3D point-cloud filtering: https://www.open3d.org/docs/release/tutorial/geometry/pointcloud_outlier_removal.html
- Open3D 0.19.0 Windows/Python wheels: https://pypi.org/project/open3d/0.19.0/
