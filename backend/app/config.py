from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    groq_api_key: str = ""
    groq_text_model: str = "llama-3.3-70b-versatile"
    groq_vision_model: str = "qwen/qwen3.6-27b"
    groq_whisper_model: str = "whisper-large-v3-turbo"
    sim_seed: int = 42
    sim_users_per_persona: int = 40
    sim_monte_carlo_runs: int = 30
    sim_max_rounds: int = 6
    port: int = 8000
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    cors_origin_regex: str = ""
    sim_api_key: str = ""
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

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


settings = Settings()
