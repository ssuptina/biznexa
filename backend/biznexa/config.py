from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://biznexa:biznexa@localhost:5432/biznexa"
    synthetic_load_enabled: bool = False
    analytics_schema: str = "public"
    frontend_origin: str = ""

    @property
    def sqlalchemy_database_url(self) -> str:
        """Return a SQLAlchemy URL using the installed psycopg driver.

        Supabase displays PostgreSQL URLs with the generic ``postgresql://``
        scheme. SQLAlchemy's generic PostgreSQL scheme defaults to psycopg2,
        while this project intentionally installs psycopg (v3). Normalize the
        scheme at the application boundary so either documented form works.
        """
        value = self.database_url.strip()
        for prefix in ("postgresql://", "postgres://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix):]
        return value

    model_config = SettingsConfigDict(
        env_file=(
            str(Path(__file__).resolve().parents[2] / ".env"),
            str(Path(__file__).resolve().parents[1] / ".env"),
            ".env",
        ),
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
