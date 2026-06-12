# backend/init_db.py
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from database import engine
from models import Base
import logging

logging.basicConfig(level=logging.INFO)
print("🚀 Создание таблиц в базе данных...")

# Создаём все таблицы
Base.metadata.create_all(bind=engine)
print("✅ Таблицы успешно созданы!")

# Проверяем существование таблиц
from sqlalchemy import inspect
inspector = inspect(engine)
tables = inspector.get_table_names()
print(f"📋 Созданные таблицы: {', '.join(tables)}")