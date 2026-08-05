# План интеграции UniServer, лидара и рейса автомобиля

## 1. Назначение и границы

Цель — связать поток состояний UniServer, непрерывный буфер профилей SICK LMS511 и существующий `Trip` в один отказоустойчивый производственный сценарий. Одна строка рабочего журнала должна соответствовать одному `Trip`, а лидарные данные — храниться как одна или несколько сессий, связанных с этим рейсом.

На этапе подготовки этого документа код приложения, модели БД, API-контракты и оборудование не изменяются.

В границы будущей реализации входят:

- кольцевой RAM-буфер lidar-профилей;
- автомат состояний одного проезда;
- фиксация подтверждённого стабильного веса;
- привязка lidar-сессии к существующему `trip_id`;
- атомарное сохранение массива профилей в JSON;
- метаданные сессии в PostgreSQL;
- read-only API единого состояния и журнала;
- новая страница «Контроль проезда» без удаления диагностических страниц.

Не входят:

- изменение CoLa-протокола и настроек LMS511;
- изменение настроек UniServer AUTO или весов;
- использование предварительного объёма в коммерческом учёте;
- хранение каждого профиля отдельной строкой PostgreSQL;
- переработка лабораторного модуля;
- WebSocket в MVP;
- автоматическое исправление повреждённой истории Alembic на production.

## 2. Результаты аудита текущего проекта

### 2.1. Получение данных весов

`backend/services/uniserver_client.py` содержит один singleton `uniserver_client`. Текущие параметры читаются по `/core/plugins/AutoScale1/Parameters`, затем `parse_weighing_result()` преобразует ответ в поля `weight`, `is_stable`, `state`, `plate_number`, `weight_type` и другие.

`backend/services/scale_monitor.py`:

- запускается из startup `backend/main.py`;
- опрашивает UniServer каждые 2 секунды, а не требуемые 500 мс;
- игнорирует данные без госномера и без положительного веса;
- реагирует на стабильные типы `БРУТТО`/`ТАРА`, но не строит автомат по `StateName`;
- считает новым событием изменение только пары `weight/is_stable` для ключа `plate_number/weight_type`;
- создаёт и завершает рейсы непосредственно через отдельные SQLAlchemy-транзакции;
- ловит ошибки БД и делает rollback, поэтому цикл продолжает работать, но повторяет попытки на следующих изменениях состояния.

Поля реального ответа `Massa`, `Stabil`, `StateName`, `State`, `Enable`, `RxPacket`, `UnitMeas` доступны внутри `full_response`. Для автомата следует использовать исходный snapshot, а не только текущую сокращённую схему `parse_weighing_result()`.

### 2.2. Где создаются и изменяются рейсы

Статически найдены независимые пути создания `Trip`:

1. `ScaleMonitor._handle_entry()` — автоматическое создание при стабильном `БРУТТО`.
2. `POST /api/weighing/start-trip` — ручное создание.
3. `POST /api/weighing/auto-trip` — ещё один автоматический путь.
4. Синхронизация истории/журнала UniServer в `routers/weighing.py`.
5. `TripCRUD.create_from_weighing()` — общий, но используется не всеми путями.
6. В `backend/main.py` сохранены отдельные legacy endpoints начала/завершения рейса.

Завершение выполняется как минимум через `ScaleMonitor._handle_exit()`, `/api/weighing/end-trip/{trip_id}`, синхронизацию журнала и `TripCRUD.update_exit_weighing()`.

Текущая защита от дублей неоднородна:

- `Trip.uniserver_code` уникален, но не всегда заполняется;
- часть путей проверяет активный рейс только для конкретного автомобиля;
- `ScaleMonitor` создаёт рейс без `uniserver_code`;
- проверка и вставка не защищены единым DB-lock/ограничением от гонки двух процессов;
- `uvicorn --reload` или несколько workers могут запустить несколько monitor-loop;
- ручной endpoint и monitor могут одновременно пройти проверку до commit.

До внедрения координатора необходимо на сервере определить, какой из найденных путей фактически считается официальным. В MVP существующая бизнес-проверка брутто/тары сохраняется; новый автомат не должен создавать параллельный `Trip` на событии `LoadScale`.

### 2.3. Текущие таблицы основного модуля

В `backend/models.py` определены:

- `carriers`;
- `vehicles`;
- `users`;
- `devices`;
- `trips`;
- `entry_measurements`;
- `exit_measurements`;
- `neural_logs`;
- `system_logs`;
- `stock_events`;
- `batch_density`;
- `uniserver_events`;
- `lidar_measurements`.

`Trip` связан 1:1 с входным и выходным измерением и 1:N с `LidarMeasurement`. Текущая `lidar_measurements` хранит массивы расстояний JSON непосредственно в БД и подходит для единичных диагностических измерений, но не для непрерывного потока профилей.

### 2.4. Текущий lidar-поток

`backend/services/lidar_client.py` предоставляет синхронные методы socket I/O:

- `get_scan_data()` отправляет `sRN LMDscandata`;
- внутри присутствуют блокирующие `time.sleep()` и `recv()`;
- `parse_raw_data()` и `parse_scan_data()` обрабатывают один telegram;
- `calculate_volume()` рассчитывает ориентировочный результат для одного набора точек и профиля кузова.

Постоянного фонового сборщика в backend нет. `GET /api/lidar/scan` выполняет один scan по запросу. Активный `LidarViewer.tsx` вызывает его каждые 2 секунды. Поэтому текущая фактическая частота определяется frontend polling и отсутствует, когда экран закрыт.

Синхронный lidar-вызов выполняется непосредственно внутри `async` endpoint и может блокировать event loop. Параллельный вызов диагностики и будущего буфера через один socket способен смешать ответы telegram. Будущий сборщик должен стать единственным владельцем чтения scan-data либо использовать общий lock; API диагностики должен получать последний snapshot из буфера, сохраняя существующий контракт `/api/lidar`.

`backend/routers/scan_3d.py` содержит RAM-сессии и интегрирование сечений методом трапеций, но требует внешнего `position_m`. Автоматический LMS511-поток сейчас не имеет измеренной позиции/скорости автомобиля. Поэтому этот алгоритм нельзя напрямую считать достоверным автоматическим объёмом.

### 2.5. Текущий frontend

`frontend/src/App.tsx` содержит две вкладки:

- «Весовой контроль» с ручными кнопками начала/завершения и журналом;
- «Лидарный контроль» с `LidarViewer`.

Маршрутизатора страниц нет; вкладки переключаются локальным состоянием. Часть компонентов вызывает абсолютный `http://localhost:8000`, хотя существует общий axios client в `frontend/src/services/api.ts`.

Новая страница может быть добавлена третьей вкладкой без удаления существующих экранов. Старые экраны на первом этапе остаются диагностическими.

### 2.6. Alembic

В локальном дереве backend видна только ревизия `20260802_01` с `down_revision = None`, создающая таблицы лабораторного MVP. Ранее `alembic upgrade head` против текущей БД завершился ошибкой: БД ссылается на отсутствующую ревизию `2d90296b1454`.

Следствия:

- новую миграцию можно подготовить как файл и проверить на отдельной временной PostgreSQL;
- нельзя применять её к production, пока отдельно не восстановлена/сопоставлена цепочка ревизий;
- запрещены `stamp`, `downgrade`, удаление таблиц и ручное изменение `alembic_version` без отдельного согласования;
- новая ревизия должна ссылаться на подтверждённую фактическую голову основной ветки миграций, а не слепо на `20260802_01`.

## 3. Целевая архитектура и владение состоянием

Должен существовать один `WeighingLidarCoordinator`, который владеет автоматом проезда. Он получает read-only scale snapshots от единственного monitor-loop и события/профили от `LidarProfileBuffer`.

`ScaleMonitor` остаётся владельцем опроса UniServer, но делегирует переходы координатору. Создание официального `Trip` продолжает выполняться по существующим правилам стабильного брутто/тары. Координатор на `LoadScale` создаёт только предварительную lidar-pass-сессию с nullable `trip_id`, а после официального создания рейса идемпотентно привязывает к ней фактический `trip.id`.

Не следует запускать отдельный второй polling UniServer для координатора: иначе появятся расходящиеся snapshots и дополнительные запросы.

Для одной весовой допускается максимум один активный coordinator session. Защита должна быть двухуровневой:

- in-process `asyncio.Lock` для сериализации переходов;
- PostgreSQL partial unique index для активной lidar-pass-сессии, чтобы защититься от второго worker/process.

Для production рекомендуется один worker для процесса, управляющего физическим socket лидара. Несколько uvicorn workers не могут безопасно разделять один in-memory deque и один TCP socket без отдельного device-agent/Redis, что выходит за MVP.

## 4. Конечный автомат состояний

| Текущее состояние | Условие | Следующее | Действия |
|---|---|---|---|
| `IDLE` | переход `StateName` в `LoadScale` | `ENTERING_AND_SCANNING` | создать одну lidar-pass-сессию, скопировать pre-trigger буфер, записать `load_scale_at` |
| `ENTERING_AND_SCANNING` | `StateName == Weighing` | `WEIGHING` | продолжать профили, начать учёт weight samples |
| `WEIGHING` | `StateName == Weighing` и `Stabil=true` подряд N раз | `WEIGHT_CAPTURED` | сохранить стабильный и максимальный вес, timestamp, запланировать post-stable stop |
| `WEIGHT_CAPTURED` | прошло `LIDAR_POST_STABLE_SECONDS` | `WEIGHT_CAPTURED` | закрыть lidar capture, атомарно сохранить JSON вне scale-loop |
| `WEIGHT_CAPTURED` | `StateName == ReadyWeighing` | `READY` | сохранить timestamp, не создавать новую lidar-сессию |
| `READY` | `StateName == WeighingComplete` | `WAITING_DEPARTURE` | сохранить timestamp, продолжить весовой сценарий |
| `WAITING_DEPARTURE` | `StateName == UnLoadScale` | `LEAVING` | сохранить timestamp |
| `LEAVING` | `Massa <= SCALE_EMPTY_THRESHOLD_KG`, `Stabil=true` подряд M раз | `COMPLETED` | завершить orchestration session, освободить active slot |
| любое активное | повторный `LoadScale` | без перехода | обновить snapshot, не создавать дубль |
| любое активное | временно нет UniServer | без ложного перехода | отметить scale disconnected, ждать восстановления |
| lidar recording | ошибка лидара | workflow продолжается | lidar status `FAILED`, весовой рейс не откатывать |

Правила подтверждения:

- сравнивать нормализованный `StateName`, но сохранять исходное значение;
- переходы выполнять по фронту состояния, а не на каждом одинаковом poll;
- stable counter сбрасывать при `Stabil=false` или уходе из `Weighing`;
- empty counter сбрасывать при весе выше порога или `Stabil=false`;
- `SCALE_STABLE_CONFIRM_SAMPLES=3`, `SCALE_EMPTY_CONFIRM_SAMPLES=3`;
- каждый переход и его timestamp хранить в `state_timestamps`.

## 5. Кольцевой буфер lidar-профилей

Новый `LidarProfileBuffer`:

1. Запускается один раз в lifespan/startup приложения.
2. Выполняет блокирующий `get_scan_data()` через `asyncio.to_thread()`.
3. Парсит один профиль и формирует:
   - `captured_at` с timezone;
   - монотонный `sequence_number`;
   - `points_total` до фильтрации;
   - `points_valid` после существующей фильтрации;
   - `distances_mm`;
   - min/max/average по валидным точкам.
4. Добавляет профиль в `deque(maxlen=LIDAR_PROFILE_MAX_COUNT)`.
5. Дополнительно удаляет элементы старше `LIDAR_BUFFER_SECONDS`, поэтому ограничение одновременно временное и количественное.
6. Пока активной сессии нет, ничего не пишет в БД/файл.
7. При `LoadScale` под lock копирует текущий deque в session accumulator и фиксирует число pre-trigger profiles.
8. Новые профили добавляются в активную сессию до post-stable deadline.

При ошибке socket сервис делает ограниченный reconnect/backoff и сообщает состояние координатору. Ошибка не должна выбрасываться в `ScaleMonitor`.

Поскольку существующий lidar client не поддерживает конкурентные запросы, доступ к socket должен быть сериализован. Предпочтительный MVP: buffer service — единственный reader, а диагностический `/api/lidar/scan` возвращает последний обработанный профиль. Это сохраняет форму API, но до реализации нужно проверить все поля ответа frontend.

## 6. Сохранение lidar-сессии

Путь:

```text
backend/data/lidar_passes/lidar_pass_<trip_id-or-pending>_<timestamp>.json
```

Алгоритм:

1. Под lock отделить завершённый immutable snapshot профилей от активного буфера.
2. Передать сериализацию и запись в `asyncio.to_thread()` или ограниченный executor.
3. Создать временный файл в том же каталоге.
4. Записать UTF-8 JSON, выполнить `flush()` и `os.fsync()`.
5. Выполнить атомарный `os.replace(temp, final)`.
6. Только после успешного rename обновить метаданные БД на `COMPLETED`.
7. При ошибке оставить вес/Trip, поставить lidar status `FAILED`, сохранить безопасный текст ошибки и удалить только собственный временный файл.

Большой JSON не записывается внутри критического 500-мс scale-loop. Одновременно допускается ограниченное число save jobs; для одной весовой достаточно одного последовательного writer-worker.

При завершении до появления `trip_id` файл временно получает session UUID. После привязки к Trip метаданные остаются источником истины; переименование файла необязательно и создаёт лишнюю точку отказа.

## 7. Схема данных

Новая таблица `lidar_pass_sessions` (без изменений существующих таблиц в MVP):

| Поле | Тип/ограничение | Назначение |
|---|---|---|
| `id` | bigint PK | идентификатор сессии |
| `trip_id` | FK `trips.id`, nullable, index | привязывается после официального создания Trip |
| `status` | enum/string | `PENDING`, `RECORDING`, `COMPLETED`, `FAILED` |
| `workflow_state` | enum/string | состояние единого автомата |
| `trigger_type` | string | `LOAD_SCALE`, позднее `MANUAL_RETRY` |
| `trigger_state_name` | string | исходное состояние UniServer |
| `started_at` | timestamptz | начало сохранённого интервала |
| `load_scale_at` | timestamptz | подтверждённый вход |
| `stable_weight_at` | timestamptz nullable | подтверждение веса |
| `ended_at` | timestamptz nullable | завершение lidar capture |
| `completed_at` | timestamptz nullable | завершение проезда |
| `pre_trigger_seconds` | float | фактически использованное окно |
| `pre_trigger_profiles_count` | integer | профилей до LoadScale |
| `profiles_count` | integer | всего профилей |
| `valid_profiles_count` | integer | профилей с валидными точками |
| `points_total` | bigint | сумма исходных точек |
| `points_valid` | bigint | сумма валидных точек |
| `trigger_weight_kg` | float nullable | масса при LoadScale |
| `stable_weight_kg` | float nullable | подтверждённая масса |
| `maximum_observed_weight_kg` | float nullable | максимум проезда |
| `weight_samples_count` | integer | число samples в сессии |
| `state_timestamps` | JSONB | timestamps переходов без добавления множества колонок |
| `estimated_volume_m3` | float nullable | только ориентировочный объём |
| `volume_status` | enum/string | `NOT_CALCULATED`, `PRELIMINARY`, `CALIBRATED`, `FAILED` |
| `data_file_path` | string nullable | относительный путь к JSON |
| `error_message` | text nullable | безопасная причина ошибки |
| `created_at`, `updated_at` | timestamptz | аудит записи |

Связь: `Trip 1 → N LidarPassSession`. `trip_id` должен быть nullable, потому что `LoadScale` наступает раньше существующего официального создания Trip.

Индексы:

- `trip_id`;
- `started_at DESC`;
- `status`;
- partial unique index, допускающий глобально только одну строку со статусом `PENDING`/`RECORDING` для этой весовой.

Добавление `lidar_pass_sessions` relationship в `Trip` допустимо как ORM-изменение без изменения существующих колонок.

## 8. Привязка к существующему Trip и защита от дублей

Безопасная последовательность:

1. На `LoadScale` координатор создаёт lidar-pass-сессию, но не создаёт `Trip`.
2. На подтверждённом стабильном брутто вызывается существующая официальная функция создания/получения рейса.
3. Функция должна вернуть существующий или новый `Trip` идемпотентно.
4. Координатор привязывает активную lidar-pass-сессию к `trip.id` в отдельной короткой транзакции.
5. Повторный вызов с тем же `trip.id` ничего не создаёт.

Перед реализацией все production-пути создания рейса следует направить через одну транзакционную функцию `TripCRUD.get_or_create_from_weighing()` либо сервис-обёртку. Старые endpoints сохраняются, но делегируют этой функции.

Минимальные DB-гарантии:

- уникальный `Trip.uniserver_code`, когда DocID присутствует;
- блокировка на время поиска/создания активного рейса (`pg_advisory_xact_lock` для одной весовой либо согласованный row lock);
- повторная проверка после получения lock;
- уникальная входная `EntryMeasurement.trip_id` уже существует;
- запрет второй активной lidar-pass-сессии partial index.

Если текущий endpoint параметров не содержит госномер/DocID, автомат не должен выдумывать автомобиль. Lidar-pass-сессия может оставаться непривязанной до появления официального Trip; оператору показывается `ожидает привязки`. Не следует создавать фиктивный `Vehicle`.

## 9. Предварительный объём

Безопасный MVP сохраняет профили и статистику, но устанавливает:

```text
estimated_volume_m3 = null
volume_status = NOT_CALCULATED
```

Причина: существующий `calculate_volume()` оценивает объём по одному профилю и заданным размерам кузова, а `scan_3d.calculate_total_volume()` требует достоверный `position_m`, которого в автоматическом потоке нет.

Экспериментальный `PRELIMINARY` можно добавить отдельным этапом только после выбора источника продольной координаты: скорость UniServer/датчик, энкодер, известная скорость проезда либо валидированный алгоритм сопоставления профилей. Результат всегда маркируется «Предварительный, не откалиброван».

## 10. API

Новый router: `/api/control`, без изменения контрактов `/api/lidar`, `/api/weighing`, `/api/camera`.

### `GET /api/control/current`

Возвращает последний scale snapshot, состояние buffer/coordinator, camera status и краткий active Trip. Endpoint не опрашивает оборудование сам, а читает последний in-memory snapshot, поэтому не создаёт дополнительную нагрузку.

### `GET /api/control/trips?limit=50&offset=0`

Возвращает одну строку на `Trip` с агрегатом последней/основной lidar-pass-сессии. Источник списка — PostgreSQL, не UniServer journal.

### `GET /api/control/trips/{trip_id}`

Детали Trip, входное/выходное измерение, переходы и агрегаты lidar-сессий. Большой массив `profiles` по умолчанию не возвращается.

### `GET /api/control/trips/{trip_id}/lidar-sessions`

Список metadata-сессий без чтения больших JSON-файлов.

### `POST /api/control/trips/{trip_id}/lidar/retry`

Отложить после MVP. Безопасен только когда подтверждено, что автомобиль всё ещё стоит; требует operator action audit и создаёт новую `MANUAL_RETRY` session, не перезаписывая старую.

Следует добавить Pydantic v2-схемы ответов и документировать все новые endpoints в OpenAPI.

## 11. Схема взаимодействия потоков

```text
                         ┌────────────────────────┐
                         │ UniServer Parameters   │
                         └───────────┬────────────┘
                                     │ один poll / 500 ms
                                     ▼
┌──────────────┐ profiles   ┌──────────────────────┐
│ SICK LMS511  ├───────────►│ LidarProfileBuffer   │
└──────────────┘             │ deque + latest state │
                             └──────────┬───────────┘
                                        │ profile events / snapshots
                                        ▼
                         ┌──────────────────────────┐
scale snapshots ────────►│ WeighingLidarCoordinator│
                         │ FSM + one active session │
                         └──────┬───────────┬───────┘
                                │           │ immutable completed profiles
                      short DB  │           ▼
                      metadata  │    ┌──────────────────┐
                                │    │ File writer task │
                                ▼    │ temp/fsync/replace│
                         ┌──────────┐└────────┬─────────┘
                         │PostgreSQL│         ▼
                         └────┬─────┘ backend/data/lidar_passes
                              │
                              ▼
                         /api/control
                              │ polling
                              ▼
                       ControlPage React
```

Камера не включается в критический путь. `/api/control/current` показывает её последний известный статус. Ошибка camera status не изменяет FSM весов/лидара.

## 12. Lifecycle и восстановление

Порядок startup:

1. Проверить конфигурацию и создать каталоги данных.
2. Проверить БД; при недоступности не запускать tight exception loop, использовать backoff.
3. Запустить lidar buffer независимо от UniServer.
4. Запустить один ScaleMonitor/Coordinator.
5. Зарегистрировать `/api/control`.

Порядок shutdown:

1. Остановить новые polls.
2. Закрыть/пометить активный lidar capture.
3. Дождаться writer task с ограниченным timeout.
4. Закрыть lidar socket.

После рестарта RAM pre-trigger buffer неизбежно пуст. Строку `PENDING`/`RECORDING`, оставшуюся в БД от погибшего процесса, следует пометить `FAILED` с причиной `backend_restarted`; нельзя притворяться, что профиль восстановлен. Если машина ещё находится на весах, оператор может позднее выполнить отдельный retry.

## 13. Frontend-сценарий

Добавить третью вкладку «Контроль проезда» и сделать её стартовой после приёмочных испытаний. В MVP она polling-читает `/api/control/current` примерно раз в 1 секунду и `/api/control/trips` после завершения/раз в несколько секунд.

Блок активного проезда:

- человекочитаемое состояние FSM;
- текущая масса и стабильность;
- доступность UniServer;
- lidar connected/recording/failed;
- число buffer/session/pre-trigger profiles;
- camera status как независимый индикатор;
- стабильный вес после фиксации;
- объём: `Ожидает расчёта` для `NOT_CALCULATED`.

Журнал: одна строка на `Trip`, колонки из ТЗ. При lidar failure явно показывать `Ошибка лидара — вес сохранён`. Старые вкладки не удалять; переименовать группу в «Диагностика оборудования» можно после MVP.

Frontend должен использовать общий API client/относительный base URL вместо новых абсолютных `localhost`-вызовов.

## 14. Файлы будущей реализации

### Изменяемые

- `backend/config.py` — новые env-настройки;
- `backend/.env.example` — безопасные значения параметров;
- `backend/models.py` — ORM `LidarPassSession` и relationship;
- `backend/services/scale_monitor.py` — 500-мс poll, raw snapshot, делегирование FSM, один владелец создания событий;
- `backend/services/lidar_client.py` — только безопасная сериализация доступа/socket lock при необходимости, без изменения протокола;
- `backend/routers/lidar.py` — чтение последнего buffer snapshot для диагностики без изменения контракта;
- `backend/main.py` — lifecycle новых сервисов и router;
- `backend/crud.py` — единая идемпотентная функция создания/получения Trip и привязки;
- `backend/routers/weighing.py` — старые endpoints делегируют единой функции;
- `frontend/src/App.tsx` — новая вкладка;
- `frontend/src/services/api.ts` — `/api/control` методы;
- `frontend/src/App.css` — стили новой страницы при необходимости.

### Новые

- `backend/services/lidar_profile_buffer.py`;
- `backend/services/weighing_lidar_coordinator.py`;
- `backend/services/lidar_pass_storage.py`;
- `backend/routers/control.py`;
- `backend/schemas/control.py`;
- `backend/alembic/versions/<revision>_add_lidar_pass_sessions.py`;
- `frontend/src/components/Control/ControlPage.tsx`;
- `frontend/src/components/Control/ActivePassCard.tsx`;
- `frontend/src/components/Control/TripsControlTable.tsx`;
- `backend/tests/test_lidar_profile_buffer.py`;
- `backend/tests/test_weighing_lidar_state_machine.py`;
- `backend/tests/test_lidar_pass_storage.py`;
- `backend/tests/test_control_api.py`.

Лабораторные файлы и API не изменяются.

## 15. Миграция

1. Сначала отдельно восстановить карту production-ревизий и найти происхождение `2d90296b1454`.
2. Получить дамп схемы/`alembic_version` только read-only.
3. Подготовить новую миграцию создания `lidar_pass_sessions`, enum/check constraints, FK и индексов.
4. Проверить upgrade на временной PostgreSQL с копией основной схемы.
5. Проверить rollback только на тестовой БД; production downgrade не выполнять.
6. Сформировать SQL (`alembic upgrade ... --sql`) и передать на ревью DBA.
7. Только после исправления цепочки и резервной копии применять к production.

Миграция не должна создавать/изменять лабораторные таблицы и не должна удалять существующие объекты.

## 16. Тесты и критерии приёмки

### Unit

- deque ограничен одновременно временем и `max_count`;
- копирование pre-trigger данных не меняет deque;
- одинаковый `LoadScale` не создаёт вторую сессию;
- краткий одиночный `Stabil=true` не фиксирует вес;
- N последовательных samples фиксируют вес один раз;
- empty подтверждается M samples;
- post-stable deadline закрывает capture;
- formatter/atomic writer создаёт валидный JSON и не оставляет final partial file;
- volume по умолчанию `NOT_CALCULATED`.

### Integration

- успешная последовательность `Empty → ... → Empty`;
- повторные одинаковые snapshots;
- lidar недоступен: Trip/EntryMeasurement сохраняются, lidar session `FAILED`;
- camera недоступна: вес и lidar продолжаются;
- UniServer потерян: ложный Trip не создаётся, восстановление продолжает FSM осторожно;
- БД потеряна: backoff без tight loop, lidar buffer остаётся ограниченным;
- два конкурентных события не создают второй Trip/session;
- restart во время машины помечает оборванную сессию и не выдаёт ложный `COMPLETED`;
- retry создаёт новую сессию на том же Trip (после MVP);
- API не возвращает массивы всех профилей в списке рейсов.

### Regression

- существующие `/api/lidar`, `/api/weighing`, `/api/camera` контракты;
- существующие ручные start/end операции;
- backend `pytest`;
- обе frontend build-команды;
- Alembic на тестовой БД;
- лабораторный API smoke test.

## 17. Основные риски и меры

| Риск | Влияние | Мера |
|---|---|---|
| Несколько путей создания Trip | дубли/неверная привязка | единая транзакционная функция, DB lock, idempotency |
| Несколько uvicorn workers/reload | два monitor-loop, два socket reader | один device worker; DB partial index; без reload в production |
| Socket читают buffer и diagnostics | смешение telegram | один reader или общий lock; diagnostics из latest snapshot |
| `LoadScale` раньше Trip | нет `trip_id` при начале | nullable FK, поздняя идемпотентная привязка |
| Parameters не содержит госномер | нельзя определить Vehicle | не выдумывать; ждать официального Trip/DocID |
| Блокирующий lidar I/O | задержка scale poll/API | `asyncio.to_thread`, отдельный service task |
| Большой RAM/JSON | исчерпание памяти/диск | time+count cap, session limits, метрики, один writer |
| Сбой во время записи | повреждённый файл | temp + fsync + atomic replace |
| Ошибка лидара | потеря веса | независимые транзакции и `FAILED` metadata |
| Недоступна БД | error storm | exponential capped backoff, throttled logs |
| Недостоверный объём | неверный учёт | `NOT_CALCULATED` в MVP, затем только `PRELIMINARY` |
| Повреждён Alembic graph | невозможен deploy | отдельный аудит `2d90296b1454`, временная БД, DBA review |
| Старый frontend localhost | не работает с другого ПК | общий axios base URL в этапе frontend |

## 18. Минимальный MVP

Минимальный безопасный объём реализации:

1. Один 500-мс ScaleMonitor с raw snapshot и FSM, без второго UniServer poller.
2. Один lidar buffer service с 5-секундным deque и max 1000.
3. Начало lidar-pass-сессии по фронту `LoadScale` с pre-trigger profiles.
4. Подтверждение стабильного веса тремя samples.
5. Остановка lidar capture через 1 секунду после stable confirmation.
6. Сохранение профилей атомарным JSON вне scale-loop.
7. Одна таблица metadata `lidar_pass_sessions`, nullable `trip_id` и поздняя привязка.
8. Сохранение существующего официального Trip/веса при lidar failure.
9. `GET /api/control/current`, `/trips`, `/trips/{id}`, `/lidar-sessions`.
10. Страница «Контроль проезда» с polling и `NOT_CALCULATED` для объёма.
11. Unit/integration тесты автомата, буфера, дублей и отказов.

## 19. Отложить после MVP

- ручной lidar retry endpoint и UI;
- подтверждённый/калиброванный 3D-объём;
- вычисление продольной координаты профиля;
- WebSocket/SSE;
- Redis/device-agent для нескольких backend workers;
- автоматическое восстановление профилей после restart;
- хранение/просмотр полного JSON через публичный API;
- camera capture orchestration и архивирование фото;
- перенос старых вкладок в полноценный router «Диагностика»;
- ретроспективная миграция старых `LidarMeasurement` в новые сессии.

## 20. Влияние на существующий работающий модуль

При соблюдении плана влияние ограничено:

- существующие API-контракты не удаляются и не переименовываются;
- существующие Trip, EntryMeasurement и ExitMeasurement сохраняются;
- новый coordinator сначала наблюдает `LoadScale`, а официальный Trip создаётся прежним правилом подтверждённого веса;
- lidar/camera failure не участвуют в транзакции сохранения веса;
- laboratory router, модели, сервисы и frontend не затрагиваются;
- новая таблица и новые endpoints добавочны;
- основное поведенческое изменение — частота ScaleMonitor с 2 с до 500 мс и появление постоянного lidar reader, поэтому нагрузочные и аппаратные испытания обязательны;
- перед production нужен запуск без `--reload`, с одним worker, тестовая миграция и наблюдение CPU/RAM/размера JSON.

## 21. Порядок внедрения

1. Уточнить production-владельца создания Trip и реальные поля Parameters во всех состояниях.
2. Отдельно решить проблему Alembic `2d90296b1454`.
3. Реализовать и unit-тестировать buffer/storage без оборудования.
4. Реализовать FSM на записанных snapshots UniServer.
5. Добавить metadata model/migration и проверить на временной PostgreSQL.
6. Подключить coordinator к существующему Trip creation через идемпотентный hook.
7. Провести стендовый replay последовательности состояний.
8. Подключить реальный lidar в режиме наблюдения, проверить частоту/память без записи Trip.
9. Включить JSON storage и отказные сценарии.
10. Добавить read-only control API.
11. После стабилизации backend добавить frontend.
12. Провести параллельную эксплуатацию со старым журналом до приёмки.

Реализацию начинать только после отдельной команды и подтверждения канонического production-пути создания рейса и стратегии исправления Alembic.
