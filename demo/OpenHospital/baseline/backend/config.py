"""Backend configuration."""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True
    redis_host: str = os.environ.get("HOSPITAL_API_REDIS_HOST", "localhost")
    redis_port: int = int(os.environ.get("HOSPITAL_API_REDIS_PORT", "6379"))
    redis_db: int = int(os.environ.get("HOSPITAL_API_REDIS_DB", "0"))
    redis_password: str = os.environ.get("HOSPITAL_API_REDIS_PASSWORD", "")
    cors_origins: list = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ] + [
        origin.strip()
        for origin in os.environ.get("HOSPITAL_API_CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]

    class Config:
        env_prefix = "HOSPITAL_API_"
        env_file = ".env"
settings = Settings()
