from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    upstage_api_key: str = Field(default="", alias="UPSTAGE_API_KEY")
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_secret_key: str = Field(default="", alias="SUPABASE_SECRET_KEY")

    backend_host: str = Field(default="0.0.0.0", alias="BACKEND_HOST")
    backend_port: int = Field(default=8000, alias="BACKEND_PORT")
    cors_allow_origins: str = Field(
        default="http://localhost:3000", alias="CORS_ALLOW_ORIGINS"
    )

    disable_rate_limit: bool = Field(default=False, alias="DISABLE_RATE_LIMIT")

    solar_model: str = Field(default="solar-pro2", alias="SOLAR_MODEL")
    solar_temperature: float = Field(default=0.2, alias="SOLAR_TEMPERATURE")
    solar_llm_timeout: float = Field(default=60.0, alias="SOLAR_LLM_TIMEOUT")
    groundedness_threshold: float = Field(default=0.7, alias="GROUNDEDNESS_THRESHOLD")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
