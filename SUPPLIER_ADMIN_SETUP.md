# Администрирование поставщиков, машин и заявленных характеристик угля

Модуль ведёт производственные справочники, но не участвует в текущих расчётах взвешивания, LiDAR или объёма.

```text
Supplier
  ├── Vehicle
  │     └── Supplier Assignment History
  └── Coal Grade / Specification
        ├── Calorific value + explicit unit
        ├── Moisture
        ├── Ash
        └── Fraction constraints

Laboratory Results
  └── remain separate actual measurements
```

Переиспользованы канонические таблицы `suppliers` и `coal_grades`, уже используемые лабораторией и приёмкой угля. Миграция `20260905_01` безопасно расширяет поставщика и добавляет `supplier_vehicles`, `vehicle_supplier_assignments`, `supplier_coal_specs`, `supplier_coal_fraction_specs`. Она не добавляет демонстрационные записи.

Назначение машины поставщику хранится периодами. Переназначение закрывает прежний открытый период и создаёт новый. Изменение заявленной спецификации выполняется созданием новой версии; старая версия закрывается предыдущим днём. Поэтому будущая сессия сможет сохранить конкретные ID назначения и спецификации без зависимости от текущих справочников.

Заявленные значения поставщика не являются лабораторными измерениями. Фактические анализы остаются исключительно в существующем лабораторном модуле и не перезаписываются.

API находится под `/api/admin`: suppliers, vehicles, vehicle supplier-history/reassign, coal-grades, coal-specs и coal-spec replacement/status. Все списки имеют server-side pagination и стабильную сортировку. UI: верхнее меню **Администрирование**, вкладки **Поставщики**, **Машины**, **Характеристики угля**.

В проекте нет реально применяемой middleware-проверки ролей для этих маршрутов. `ADMIN_AUTHORIZATION_AVAILABLE = NO`; перед внешней публикацией API требуется подключить общую авторизацию, когда она появится.

Развёртывание после получения кода:

```powershell
cd C:\Users\lemeshkov\weight-control\backend
..\venv_weight\Scripts\alembic.exe upgrade head
..\venv_weight\Scripts\python.exe -m pytest tests/test_supplier_admin.py -q
cd ..\frontend
npm run build
```

Откат до предыдущей схемы допустим только после проверки отсутствия нужных административных данных: `alembic downgrade 20260809_01`. Production database в ходе разработки не изменялась.
