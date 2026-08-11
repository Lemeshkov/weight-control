# Cross-session Camera Motion Metric Research

Исследованы три реальные сессии как DEVELOPMENT data. TEST B сохраняет роль `TUNING`,
две бывшие validation-сессии после просмотра их результатов больше не являются holdout.

## Почему старый candidate отклонён

Старый score — медиана Farneback по full frame. На TEST B median MOVING равен примерно
`0.3486`, но в двух следующих сессиях — `8.30e-06` и `8.53e-06`, то есть ниже frozen
STOP threshold `1.361371e-05`. Большую часть кадра занимает неподвижный фон; при меньшей
площади кузова его нулевой flow доминирует над медианой.

Дополнительно ground truth новых записей не задаёт интервал присутствия автомобиля.
В `c65c0b…` длительная начальная часть — пустой статичный кадр, хотя правило разметки
считает всё до STOPPED состоянием MOVING. В `0700fa…` почти весь `no-stop` dataset также
показывает пустой путь, а машина входит только в конце. Motion detector не может отличить
«пустой статичный кадр, названный MOVING» от «неподвижного кузова» без отдельного сигнала
vehicle presence.

## Сравнённые метрики

На фиксированном масштабе 256×144 рассчитаны raw median, median/p75/p90 по пикселям с
фиксированной gradient threshold, flow/gradient normalization, active-pixel ratio,
spatial adaptive noise floor, median/p75 по сетке 4×8 tiles и active-tile ratio.
Также записаны brightness, contrast, gradient energy, changed pixels, frame intervals,
motion geometry и foreground относительно первых десяти кадров без использования markers.

На `c65c0b…` informative-flow p75 имеет median MOVING `0.02585`, а STOPPED `0.02952`;
active-pixel ratio — `0.07066` против `0.07201`. Таким образом labels перекрываются и
даже меняют ожидаемый порядок. Все десять pooled attempts смогли удовлетворить только
одну из трёх сессий. Лучший objective оказался вырожденным always-MOVING: false STOP 0,
но STOP не обнаружен в обеих stop-resume сессиях и false MOVING составляет 35.344 s.
Он намеренно не опубликован как candidate.

Frame interval стабилен: median 219 ms, p90 около 281 ms во всех сессиях. Интервалов
более 500 ms: 4, 14 и 9. Это отдельные stalls, но они не объясняют минуты false STOP.
Brightness близка (0.428–0.442), тогда как contrast/gradient TEST B выше, что меняет
flow observability. Farneback 256×144 занимает примерно 19–20 ms на пару кадров.

## Решение

- `OLD CANDIDATE REJECTED`.
- `NEW CANDIDATE NOT READY`.
- validation pipeline v2 не создаётся до появления идентифицируемой ground truth.

Следующие записи должны отдельно размечать active interval markers
`VEHICLE_ENTERED`/`VEHICLE_EXITED` и STOPPED/RESUMED внутри него. Нужны минимум:
stop-resume, непрерывный no-stop с кузовом
в кадре, медленный проезд, короткая остановка и разные освещение/кузова. Только после
этого можно на DEVELOPMENT-наборе заморозить presence gate + spatial flow candidate,
а затем проверить его на новых unseen проездах.

Полные данные находятся в `diagnostics/motion_metric_research/`:
`cross_session_summary.json`, `cross_session_scores.csv`, `score_distributions.png` и
`session_comparison.png`. Папка `diagnostics/` не предназначена для Git.
