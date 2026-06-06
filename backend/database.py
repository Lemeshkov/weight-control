# backend/database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

# Получаем DATABASE_URL из .env или используем значение по умолчанию
DATABASE_URL = os.getenv("DATABASE_URL")

# Если DATABASE_URL не задан в .env, пытаемся импортировать из config
if not DATABASE_URL:
    try:
        from config import settings  # Убрали 'app.'
        DATABASE_URL = settings.DATABASE_URL
    except ImportError:
        # Фолбэк на значение по умолчанию
        DATABASE_URL = "postgresql://weight_user:weight_pass@localhost:5433/weight_control"

# Настройки пула соединений для production
IS_PRODUCTION = os.getenv("ENVIRONMENT", "development") == "production"

if IS_PRODUCTION:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_recycle=3600,
        echo=False
    )
else:
    # Для разработки - проще настройки
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        echo=False,
        connect_args={
            "connect_timeout": 10,
        }
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """Dependency для получения сессии БД"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Создание всех таблиц (только для разработки)"""
    import models  # Убрали 'app.'
    Base.metadata.create_all(bind=engine)
    print(" Database tables created")

def drop_db():
    """Удаление всех таблиц (осторожно!)"""
    Base.metadata.drop_all(bind=engine)
    print(" Database tables dropped")