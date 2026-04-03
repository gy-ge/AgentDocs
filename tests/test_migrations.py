import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import get_settings


def test_alembic_upgrade_creates_expected_tables(tmp_path, monkeypatch):
    database_path = tmp_path / "migrated.db"
    monkeypatch.setenv("SQLITE_PATH", str(database_path))
    get_settings.cache_clear()

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")

    connection = sqlite3.connect(database_path)
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    finally:
        connection.close()
        get_settings.cache_clear()

    table_names = {row[0] for row in rows}
    assert {
        "alembic_version",
        "documents",
        "tasks",
        "doc_versions",
        "task_templates",
    } <= table_names


def test_alembic_upgrade_creates_missing_sqlite_parent_directories(
    tmp_path, monkeypatch
):
    database_path = tmp_path / "nested" / "db" / "migrated.db"
    monkeypatch.setenv("SQLITE_PATH", str(database_path))
    get_settings.cache_clear()

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")

    try:
        assert database_path.exists()
    finally:
        get_settings.cache_clear()
