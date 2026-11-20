from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    plane_base_url: str = "http://localhost:8000"
    plane_api_key: str = ""
    plane_workspace_slug: str = ""

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"  # fast (~1-2 s): reports are short prose from computed data
    gemini_fallback_model: str = "gemini-3.5-flash,gemini-flash-latest"  # tried in order when the main model is overloaded

    database_path: str = "./data/orbit.db"
    orbit_internal_token: str = "change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()
