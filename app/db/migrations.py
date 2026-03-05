from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError


def run_simple_migrations(engine: Engine) -> None:
    """
    Простые "миграции" для SQLite.

    Сейчас:
    - добавляет колонку pgn в таблицу matches, если её нет.
    """
    with engine.begin() as conn:
        try:
            conn.execute(text("ALTER TABLE matches ADD COLUMN pgn TEXT"))
        except OperationalError:
            pass
        for col, col_type in [
            ("venue", "VARCHAR(255)"),
            ("prize_fund", "VARCHAR(100)"),
        ]:
            try:
                conn.execute(text(f"ALTER TABLE tournaments ADD COLUMN {col} {col_type}"))
            except OperationalError:
                pass

