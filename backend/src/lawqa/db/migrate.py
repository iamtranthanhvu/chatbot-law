from pathlib import Path

from alembic import command
from alembic.config import Config

_BACKEND_DIR = Path(__file__).resolve().parents[3]


def alembic_config(database_url: str | None = None) -> Config:
    config = Config(str(_BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    if database_url:
        config.set_main_option("sqlalchemy.url", database_url)
    return config


def upgrade(database_url: str | None = None, revision: str = "head") -> None:
    command.upgrade(alembic_config(database_url), revision)


def downgrade(database_url: str | None = None, revision: str = "-1") -> None:
    command.downgrade(alembic_config(database_url), revision)
