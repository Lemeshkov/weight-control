# backend/config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://weight_user:weight_pass@localhost:5433/weight_control")
    
    # UniServer API
    UNISERVER_URL: str = os.getenv("UNISERVER_URL", "http://185.30.12.108:8087")
    UNISERVER_USER: str = os.getenv("UNISERVER_USER", "user")
    UNISERVER_PASSWORD: str = os.getenv("UNISERVER_PASSWORD", "user")
    UNISERVER_TIMEOUT: int = int(os.getenv("UNISERVER_TIMEOUT", "30"))
    
    # File storage
    PHOTO_STORAGE_PATH: str = os.getenv("PHOTO_STORAGE_PATH", "/data/photos")
    ARCHIVE_PATH: str = os.getenv("ARCHIVE_PATH", "/data/archive")
    
    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

# Создаем экземпляр настроек
settings = Settings()