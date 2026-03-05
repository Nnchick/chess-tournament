from pathlib import Path
from typing import Final

from pydantic_settings import BaseSettings


BASE_DIR: Final[Path] = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """
    Application settings.

    For учебный (дипломный) проект достаточно SQLite по умолчанию.
    При необходимости строку подключения можно переопределить через переменные окружения.
    """

    app_name: str = "Chess Swiss Tournament Service"
    sqlite_path: Path = BASE_DIR / "data" / "db.sqlite3"

    @property
    def database_url(self) -> str:
        """
        Build SQLAlchemy database URL for SQLite.

        Returns:
            str: Database connection URL.
        """
        return f"sqlite:///{self.sqlite_path}"


settings = Settings()
# Гарантируем, что папка для БД существует, чтобы избежать ошибки
# sqlite3.OperationalError: unable to open database file
settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

