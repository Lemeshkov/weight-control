#!/bin/bash

# scripts/setup_database.sh
echo "=== Setting up database for Weight Control System ==="

# Переходим в корень проекта (где находится alembic.ini)
cd "$(dirname "$0")/.." || exit

# 1. Проверяем запущен ли PostgreSQL
echo "Checking PostgreSQL connection..."
if ! docker-compose exec -T postgres pg_isready -U weight_user; then
    echo "Starting PostgreSQL..."
    docker-compose up -d postgres
    sleep 5
fi

# 2. Устанавливаем Alembic если не установлен
if ! command -v alembic &> /dev/null; then
    echo "Installing Alembic..."
    pip install alembic
fi

# 3. Инициализируем Alembic если не инициализирован
if [ ! -d "alembic" ]; then
    echo "Initializing Alembic..."
    alembic init alembic
    echo "✓ Alembic initialized"
fi

# 4. Настраиваем alembic.ini (автоматически)
echo "Configuring alembic.ini..."
if ! grep -q "sqlalchemy.url = postgresql://weight_user:weight_pass@localhost:5432/weight_control" alembic.ini; then
    sed -i 's|sqlalchemy.url = .*|sqlalchemy.url = postgresql://weight_user:weight_pass@localhost:5432/weight_control|' alembic.ini
    echo "✓ alembic.ini configured"
fi

# 5. Создаем миграцию
echo "Creating migration..."
alembic revision --autogenerate -m "Initial migration"

# 6. Применяем миграцию
echo "Applying migration..."
alembic upgrade head

# 7. Проверяем созданные таблицы
echo -e "\nVerifying tables..."
docker-compose exec -T postgres psql -U weight_user -d weight_control -c "\dt"

echo -e "\n=== Database setup complete! ==="