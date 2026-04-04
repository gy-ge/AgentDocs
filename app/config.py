from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AgentDocs"
    api_key: str = "change-me"
    sqlite_path: str = "data/doc.db"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def sqlite_url(self) -> str:
        db_path = Path(self.sqlite_path)
        return f"sqlite:///{db_path.as_posix()}"


def ensure_sqlite_parent_dir(sqlite_path: str) -> None:
    if sqlite_path == ":memory:":
        return

    parent_dir = Path(sqlite_path).expanduser().parent
    if parent_dir == Path("."):
        return

    parent_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
