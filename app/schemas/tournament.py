from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TournamentBase(BaseModel):
    """Общие поля турнира, используемые в нескольких схемах."""

    name: str = Field(..., max_length=200, description="Название турнира")
    rounds: int = Field(..., ge=1, le=20, description="Количество туров")
    time_control: Optional[str] = Field(
        default=None, max_length=50, description="Контроль времени (например, 10+5)"
    )
    max_players: Optional[int] = Field(
        default=None, ge=2, description="Максимальное количество участников"
    )
    venue: Optional[str] = Field(
        default=None, max_length=255, description="Место проведения"
    )
    prize_fund: Optional[str] = Field(
        default=None, max_length=100, description="Призовой фонд (например: 50 000 руб)"
    )


class TournamentCreate(TournamentBase):
    """Схема для создания турнира."""

    pass


class TournamentInDB(TournamentBase):
    """Схема турнира, как он хранится в базе данных."""

    id: int
    status: str
    start_date: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class TournamentListItem(TournamentInDB):
    """Упрощённое представление турнира для списка."""

    pass

