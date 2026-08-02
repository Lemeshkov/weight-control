##  AGENTS.md


```markdown
# Project rules

## Backend

- **Python**: 3.11+
- **Framework**: FastAPI
- **ORM**: SQLAlchemy 2.x
- **Validation**: Pydantic v2
- **Database**: PostgreSQL
- **Migrations**: Alembic
- **Logging**: loguru

## Frontend

- **Framework**: React
- **Build tool**: Vite
- **Language**: TypeScript (предпочтительно) или JavaScript
- **UI**: Существующие компоненты и стили должны сохраняться

## Architecture

- Приложение состоит из двух бизнес-модулей:
  1. **Основной модуль** — взвешивание, рейсы, управление лидаром
  2. **Лабораторный модуль** — эксперименты, анализ, исследования
- Оба модуля используют одну базу данных PostgreSQL.
- Общие сущности (модели, схемы) находятся в `backend/models/shared.py` и `backend/schemas/shared.py`.
- Модульная логика (эксперименты) должна быть изолирована в `backend/services/lab/` и не должна быть помещена в общие сервисы.
- **Не изменять существующие API контракты** (для `/api/lidar`, `/api/weighing`, `/api/camera`) без явного согласования.

## Workflow

- **Ветки**: `main` — продакшн, `develop` — разработка, `feature/*` — новые фичи
- **Миграции**: проверять на тестовой БД перед применением к production
- **Тесты**: перед завершением задачи обязательно запускать тесты бэкенда и сборку фронтенда
- **Документация**: обновлять Swagger/OpenAPI для всех новых эндпоинтов

## Before completion checklist 

- [ ] Запущены тесты бэкенда (`pytest`)
- [ ] Запущена сборка фронтенда (`npm run build`)
- [ ] Проверена миграция Alembic (`alembic upgrade head`)
- [ ] Составлен список измененных файлов
- [ ] Описаны оставшиеся риски и планы по их устранению