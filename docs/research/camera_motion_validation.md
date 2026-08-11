# Camera motion: independent offline validation

Validation использует зафиксированный на TEST B кандидат и никогда не подбирает
параметры по проверяемой сессии:

- algorithm: Farneback full-frame;
- stop threshold: `1.361371e-05`;
- start threshold: `0.00887307`;
- STOP confirmation: `2000 ms`;
- RESUME confirmation: `750 ms`.

Критерии также фиксируются до получения новых данных. Для `stop-resume`: нет ложных
STOP/RESUME transitions, задержки не более 3000/1500 ms, ошибочно заморожено не более
5% moving profiles, ошибочно принято не более 15% stationary profiles, correct time
fraction не менее 90%. Для `no-stop`: ни одного false STOP transition, нулевая false
STOP duration и ни одного ошибочно замороженного moving profile.

## Ground-truth markers

Поддерживаются `MOVING`, `STOPPED`, `RESUMED`, `VEHICLE_ENTERED` и
`VEHICLE_EXITED`. Это только diagnostic annotations в существующем
`markers.jsonl`; они не управляют Trip, FSM, LiDAR или lifecycle записи.

Active interval задаётся как `[VEHICLE_ENTERED, VEHICLE_EXITED)`. Вне него
ground truth равен `NO_VEHICLE`, camera metrics не считаются, а LiDAR profile
получает `EXCLUDE`.

## Новый проезд с остановкой

1. Запустить backend и проверить, что diagnostic recording active.
2. При появлении машины в рабочей зоне отправить `VEHICLE_ENTERED`.
3. При полной остановке отправить `STOPPED`.
4. При фактическом начале движения отправить `RESUMED`.
5. После полного выхода из рабочей зоны отправить `VEHICLE_EXITED`.
6. Выполнить explicit diagnostic finish.
6. Скопировать всю папку новой session в локальную `diagnostics/`.
7. Из папки `backend` выполнить:

```powershell
..\venv_weight\Scripts\python.exe scripts\validate_camera_motion.py `
  ..\diagnostics\<NEW_SESSION_KEY> `
  --scenario stop-resume
```

Обязателен строгий порядок `VEHICLE_ENTERED < STOPPED < RESUMED < VEHICLE_EXITED`.
Если хотя бы одного marker нет или порядок некорректен, результат будет
`GROUND_TRUTH_INCOMPLETE`; отсутствие marker никогда не трактуется как `NO_STOP`.

## Проезд без остановки

Оператор заранее выбирает сценарий без остановки: при входе ставит
`VEHICLE_ENTERED`, при полном выходе — `VEHICLE_EXITED`, затем выполняет finish.
Обязателен порядок `VEHICLE_ENTERED < VEHICLE_EXITED`. После копирования выполнить:

```powershell
..\venv_weight\Scripts\python.exe scripts\validate_camera_motion.py `
  ..\diagnostics\<NEW_SESSION_KEY> `
  --scenario no-stop
```

Именно явный `--scenario no-stop` задаёт ground truth `MOVING` на всём интервале.

## Готовые PowerShell-команды

```powershell
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/camera/debug/diagnostics/marker' -ContentType 'application/json' -Body '{"label":"VEHICLE_ENTERED"}'
```

```powershell
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/camera/debug/diagnostics/marker' -ContentType 'application/json' -Body '{"label":"STOPPED"}'
```

```powershell
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/camera/debug/diagnostics/marker' -ContentType 'application/json' -Body '{"label":"RESUMED"}'
```

```powershell
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/camera/debug/diagnostics/marker' -ContentType 'application/json' -Body '{"label":"VEHICLE_EXITED"}'
```

```powershell
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/camera/debug/diagnostics/finish'
```

Отчёт находится в:

```text
diagnostics/<NEW_SESSION_KEY>/motion_validation/validation_summary.json
```

Рядом создаются `camera_validation.csv`, `profile_acceptance.csv` и
`validation_plot.png`. `UNKNOWN` profile получает action `UNKNOWN`, а не скрытый
`ACCEPT` или `FREEZE`. Симуляция отвечает только на вопрос продолжать или заморозить
продвижение по Y; метрический longitudinal displacement она не вычисляет.

## Несколько validation sessions

```powershell
..\venv_weight\Scripts\python.exe scripts\summarize_motion_validation.py `
  ..\diagnostics
```

Агрегатор создаёт `diagnostics/motion_validation_summary.json` и CSV. TEST B
`9fafd185315e4b8194d7b59b5afb6f39` помечается `TUNING`, показывается в списке, но
не включается в independent validation totals и success rate.

До нескольких unseen validation sessions detector не подключается к production
решениям. Следующий возможный этап — отдельный feature-flagged shadow provider.
