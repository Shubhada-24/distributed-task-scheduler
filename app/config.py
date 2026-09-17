"""Application configuration classes loaded from environment variables."""

from __future__ import annotations

import os
from datetime import timedelta

def _build_mysql_uri() -> str:
    host = os.getenv("MYSQL_HOST", "localhost")
    port = os.getenv("MYSQL_PORT", "3306")
    user = os.getenv("MYSQL_USER", "scheduler")
    password = os.getenv("MYSQL_PASSWORD", "scheduler_pass")
    database = os.getenv("MYSQL_DATABASE", "task_scheduler")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"


class Config:
    """Base configuration shared by all environments."""

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }
    JSON_SORT_KEYS = False

    NUM_WORKERS = int(os.getenv("NUM_WORKERS", "3"))
    SCHEDULER_POLL_INTERVAL = float(os.getenv("SCHEDULER_POLL_INTERVAL", "1.0"))
    WORKER_HEARTBEAT_INTERVAL = float(os.getenv("WORKER_HEARTBEAT_INTERVAL", "5.0"))
    WORKER_OFFLINE_THRESHOLD = timedelta(seconds=30)
    DEFAULT_MAX_RETRIES = 3
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    SWAGGER = {
        "title": "Distributed Task Scheduler API",
        "uiversion": 3,
        "specs_route": "/api/docs/",
    }


class DevelopmentConfig(Config):
    """Local development — MySQL by default, optional DATABASE_URL override."""

    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or _build_mysql_uri()
    if (SQLALCHEMY_DATABASE_URI or "").startswith("sqlite"):
        SQLALCHEMY_ENGINE_OPTIONS = {
            "connect_args": {"check_same_thread": False},
        }


class TestingConfig(Config):
    """File-backed SQLite for multi-threaded worker tests (set in conftest)."""

    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "TEST_DATABASE_URL", "sqlite:///test_scheduler.db"
    )
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"check_same_thread": False},
    }
    NUM_WORKERS = 1
    SCHEDULER_POLL_INTERVAL = 0.1
    WORKER_HEARTBEAT_INTERVAL = 0.5
    # Disable background threads during most unit tests unless explicitly started
    AUTO_START_RUNTIME = False


class ProductionConfig(Config):
    """Production settings — secrets must come from the environment."""

    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or _build_mysql_uri()


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
