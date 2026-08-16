from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Future Oracle"
    database_url: str = "postgresql+psycopg://future_oracle:future_oracle@db:5432/future_oracle"
    cors_origins: str = "http://localhost:5173"
    met_user_agent: str = "FutureOracle/1.0 github.com/your-username/future-oracle"
    request_timeout_seconds: float = 10.0
    scheduler_enabled: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
