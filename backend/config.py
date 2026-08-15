# backend/config.py
import os
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://weight_user:weight_pass@localhost:5433/weight_control")
    
    # UniServer API
    UNISERVER_URL: str = os.getenv("UNISERVER_URL", "http://10.79.24.2:8087")
    UNISERVER_USER: str = os.getenv("UNISERVER_USER", "user")
    UNISERVER_PASSWORD: str = os.getenv("UNISERVER_PASSWORD", "user")
    UNISERVER_TIMEOUT: int = int(os.getenv("UNISERVER_TIMEOUT", "30"))

    # Unified weighing/lidar control
    SCALE_POLL_INTERVAL_MS: int = int(os.getenv("SCALE_POLL_INTERVAL_MS", "500"))
    SCALE_EMPTY_THRESHOLD_KG: float = float(os.getenv("SCALE_EMPTY_THRESHOLD_KG", "100"))
    SCALE_STABLE_CONFIRM_SAMPLES: int = int(os.getenv("SCALE_STABLE_CONFIRM_SAMPLES", "3"))
    SCALE_EMPTY_CONFIRM_SAMPLES: int = int(os.getenv("SCALE_EMPTY_CONFIRM_SAMPLES", "3"))
    LIDAR_BUFFER_SECONDS: float = float(os.getenv("LIDAR_BUFFER_SECONDS", "5"))
    LIDAR_POST_STABLE_SECONDS: float = float(os.getenv("LIDAR_POST_STABLE_SECONDS", "1"))
    LIDAR_PROFILE_MAX_COUNT: int = int(os.getenv("LIDAR_PROFILE_MAX_COUNT", "1000"))
    LIDAR_RECONNECT_SECONDS: float = float(os.getenv("LIDAR_RECONNECT_SECONDS", "2"))
    LIDAR_PASS_DATA_PATH: str = os.getenv(
        "LIDAR_PASS_DATA_PATH",
        os.path.join(os.path.dirname(__file__), "data", "lidar_passes"),
    )
    
    # Camera
    CAMERA_TYPE: str = os.getenv("CAMERA_TYPE", "ip")
    CAMERA_IP: str = os.getenv("CAMERA_IP", "192.168.1.64")
    CAMERA_PORT: int = int(os.getenv("CAMERA_PORT", "80"))
    CAMERA_USERNAME: str = os.getenv("CAMERA_USERNAME", "admin")
    CAMERA_PASSWORD: str = os.getenv("CAMERA_PASSWORD", "Hikvision")
    CAMERA_RTSP_PATH: str = os.getenv("CAMERA_RTSP_PATH", "/Streaming/Channels/101")
    CAMERA_CAPTURE_MODE: str = os.getenv("CAMERA_CAPTURE_MODE", "snapshot").strip().lower()
    CAMERA_RTSP_FALLBACK_TO_SNAPSHOT: bool = os.getenv(
        "CAMERA_RTSP_FALLBACK_TO_SNAPSHOT", "true"
    ).lower() in {"1", "true", "yes", "on"}
    CAMERA_RTSP_RECONNECT_SECONDS: float = float(os.getenv("CAMERA_RTSP_RECONNECT_SECONDS", "1"))

    # Opt-in Camera + LiDAR research recording. Disabled by default.
    CAMERA_LIDAR_DIAGNOSTIC_RECORDING: bool = os.getenv(
        "CAMERA_LIDAR_DIAGNOSTIC_RECORDING", "false"
    ).lower() in {"1", "true", "yes", "on"}
    DIAGNOSTIC_DATA_DIR: str = os.getenv(
        "DIAGNOSTIC_DATA_DIR", os.path.join(os.path.dirname(__file__), "data", "diagnostics")
    )
    DIAGNOSTIC_MAX_DURATION_SEC: int = int(os.getenv("DIAGNOSTIC_MAX_DURATION_SEC", "900"))
    DIAGNOSTIC_QUEUE_SIZE: int = int(os.getenv("DIAGNOSTIC_QUEUE_SIZE", "500"))
    DIAGNOSTIC_MAX_BYTES: int = int(os.getenv("DIAGNOSTIC_MAX_BYTES", str(2 * 1024 * 1024 * 1024)))
    DIAGNOSTIC_CAMERA_MAX_FPS: float = float(os.getenv("DIAGNOSTIC_CAMERA_MAX_FPS", "5"))
    CAMERA_LIDAR_DIAGNOSTIC_EXTENDED_SESSION: bool = os.getenv(
        "CAMERA_LIDAR_DIAGNOSTIC_EXTENDED_SESSION", "false"
    ).lower() in {"1", "true", "yes", "on"}
    DEVELOPMENT_MOTION_SHADOW_ENABLED: bool = os.getenv(
        "DEVELOPMENT_MOTION_SHADOW_ENABLED", "false"
    ).lower() in {"1", "true", "yes", "on"}
    DIAGNOSTIC_POST_FINALIZE_GRACE_SEC: float = float(
        os.getenv("DIAGNOSTIC_POST_FINALIZE_GRACE_SEC", "60")
    )

    # File storage
    PHOTO_STORAGE_PATH: str = os.getenv("PHOTO_STORAGE_PATH", "/data/photos")
    ARCHIVE_PATH: str = os.getenv("ARCHIVE_PATH", "/data/archive")
    
    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    COAL_ACCEPTANCE_WEIGHT_TOLERANCE: Decimal = Decimal(os.getenv("COAL_ACCEPTANCE_WEIGHT_TOLERANCE", "0.015"))
    COAL_ACCEPTANCE_LOCAL_TIMEZONE: str = os.getenv("COAL_ACCEPTANCE_LOCAL_TIMEZONE", "Asia/Krasnoyarsk")

# Создаем экземпляр настроек
settings = Settings()
