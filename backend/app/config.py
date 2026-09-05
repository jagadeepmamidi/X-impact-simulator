import json
import re
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: Literal["development", "test", "production"] = "development"
    groq_api_key: str = ""
    groq_text_model: str = "llama-3.3-70b-versatile"
    groq_vision_model: str = "qwen/qwen3.6-27b"
    groq_whisper_model: str = "whisper-large-v3-turbo"
    groq_timeout_seconds: float = Field(default=30.0, ge=1.0, le=120.0)
    groq_max_retries: int = Field(default=1, ge=0, le=5)
    sim_seed: int = Field(default=42, ge=0, le=2**63 - 1)
    sim_users_per_persona: int = Field(default=40, ge=1, le=500)
    sim_monte_carlo_runs: int = Field(default=30, ge=1, le=500)
    sim_max_rounds: int = Field(default=6, ge=1, le=20)
    port: int = Field(default=8000, ge=1, le=65_535)
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    cors_origin_regex: str = ""
    sim_api_key: str = ""
    sim_access_keys_json: str = ""
    rate_limit_requests: int = Field(default=60, ge=0, le=100_000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=86_400)
    rate_limit_max_clients: int = Field(default=10_000, ge=100, le=1_000_000)
    trusted_proxy_cidrs: str = ""
    max_text_chars: int = Field(default=10_000, ge=1, le=1_000_000)
    max_images: int = Field(default=5, ge=0, le=20)
    max_image_bytes: int = Field(default=8 * 1024 * 1024, ge=1)
    max_video_bytes: int = Field(default=32 * 1024 * 1024, ge=1)
    max_total_upload_bytes: int = Field(default=40 * 1024 * 1024, ge=1)
    max_request_bytes: int = Field(default=44 * 1024 * 1024, ge=1)
    upload_chunk_bytes: int = Field(default=64 * 1024, ge=1024, le=1024 * 1024)
    storage_backend: Literal["sqlite"] = "sqlite"
    allow_sqlite_in_production: bool = False
    run_retention_days: int = Field(default=0, ge=0, le=3_650)

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def groq_enabled(self) -> bool:
        return bool(self.groq_api_key.strip())

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def trusted_proxy_list(self) -> list[str]:
        return [item.strip() for item in self.trusted_proxy_cidrs.split(",") if item.strip()]

    @property
    def sim_access_key_map(self) -> dict[str, str]:
        raw = self.sim_access_keys_json.strip()
        if not raw:
            return {}
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("SIM_ACCESS_KEYS_JSON must be a JSON object") from exc
        if not isinstance(value, dict):
            raise ValueError("SIM_ACCESS_KEYS_JSON must be a JSON object")
        result: dict[str, str] = {}
        for owner_id, access_key in value.items():
            if not isinstance(owner_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", owner_id):
                raise ValueError("SIM_ACCESS_KEYS_JSON owner ids must use 1-64 letters, digits, '_' or '-'")
            if owner_id in {"admin", "development"}:
                raise ValueError(f"SIM_ACCESS_KEYS_JSON owner id '{owner_id}' is reserved")
            if not isinstance(access_key, str) or not access_key.strip():
                raise ValueError(f"SIM_ACCESS_KEYS_JSON key for '{owner_id}' must be non-empty")
            result[owner_id] = access_key.strip()
        if len(set(result.values())) != len(result):
            raise ValueError("SIM_ACCESS_KEYS_JSON keys must be unique per owner")
        return result

    @model_validator(mode="after")
    def validate_deployment_safety(self) -> "Settings":
        access_keys = self.sim_access_key_map
        if self.max_total_upload_bytes > self.max_request_bytes:
            raise ValueError("MAX_REQUEST_BYTES must be at least MAX_TOTAL_UPLOAD_BYTES")
        if self.max_image_bytes > self.max_total_upload_bytes:
            raise ValueError("MAX_IMAGE_BYTES cannot exceed MAX_TOTAL_UPLOAD_BYTES")
        if self.max_video_bytes > self.max_total_upload_bytes:
            raise ValueError("MAX_VIDEO_BYTES cannot exceed MAX_TOTAL_UPLOAD_BYTES")
        if self.sim_api_key.strip() and self.sim_api_key.strip() in access_keys.values():
            raise ValueError("SIM_API_KEY must differ from every SIM_ACCESS_KEYS_JSON user key")
        if self.is_production and not self.sim_api_key.strip() and not access_keys:
            raise ValueError("SIM_API_KEY or SIM_ACCESS_KEYS_JSON is required when APP_ENV=production")
        if self.is_production and self.storage_backend == "sqlite" and not self.allow_sqlite_in_production:
            raise ValueError(
                "SQLite is a single-node development store; set up a durable production store "
                "or explicitly acknowledge the risk with ALLOW_SQLITE_IN_PRODUCTION=true"
            )
        if self.is_production and self.run_retention_days <= 0:
            raise ValueError("RUN_RETENTION_DAYS must be set when APP_ENV=production")
        return self


settings = Settings()
