# Приёмка угля — mapping Excel

Источник: `docs/reference/08 Отчет_приемка угля.xlsx`; оригинал не изменяется. Рабочие листы: `08.26`, `Центральная ТЭЦ`, `1а-2а перемещение`. X:BA — служебные/сводные и в MVP UI не вводятся.

| Excel | Поле | Источник | Режим |
|---|---|---|---|
| A | № п/п | номер строки | export |
| B | Дата отгрузки | `shipment_date` | manual |
| C | № акта | `act_number` | manual |
| D | № ТН | `transport_invoice_number` | manual |
| E | Масса по ТН, т | `document_net_weight_t Numeric(18,3)` | manual |
| F | Фактический нетто-вес | `(брутто - тара) / 1000` | automatic |
| G | Оприходовано | `E - K - M + L` | calculated |
| H | Расхождение | `F - E` | calculated |
| I | Допустимое расхождение | `ROUND(E × tolerance, 3)`, default 0.015 | calculated |
| J | Естественная убыль | 0 в MVP | requires_business_rule |
| K | Недостача | `H>0 → 0; abs(H)<I → 0; иначе abs(H)` | calculated |
| L | Излишки | `H<0 → 0; abs(H)>I → abs(H); иначе 0` | calculated |
| M | К списанию | 0 в MVP | requires_business_rule |
| N | Грузоотправитель | существующий `suppliers` | directory |
| O | Марка угля | существующий `coal_grades` | directory |
| P | Номер УК | `uk_number` | manual |
| Q | Госномер | `Trip.vehicle.plate_number` | automatic |
| R | Приёмка, местное время | `exit_time`, иначе `entry_time` | automatic |
| S | Приёмка, МСК | конвертация R в `Europe/Moscow` | calculated |
| T | Приёмосдатчик | `receiver_name` | manual |
| U | № СФ | `invoice_number` | manual |
| V | Дата договора | до 08:00 предыдущая дата, с 08:00 текущая | calculated |
| W | Принято за сутки | сумма G по V | export aggregate |

Один `Trip` имеет максимум одну карточку (`UNIQUE trip_id`). Вес, номер и время не копируются. До появления тары нетто равно `null`; lidar-вес его не заменяет. Расчёты выполняются Decimal с точностью 0.001 т.

Требуют бизнес-подтверждения: формулы J/M и необходимость полного воспроизведения сводных X:BA. В MVP завершение без тары запрещено.
