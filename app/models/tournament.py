from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class TournamentStatus(str):
    """Простейший тип статуса турнира (можно заменить на Enum при необходимости)."""

    PLANNED = "planned"
    REGISTRATION = "registration"
    RUNNING = "running"
    FINISHED = "finished"


class Tournament(Base):
    """
    Модель турнира.

    Здесь описывается только базовая информация.
    В следующих этапах добавим связи с раундами, партиями и участниками.
    """

    __tablename__ = "tournaments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    time_control: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    max_players: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    venue: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    prize_fund: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=TournamentStatus.PLANNED
    )
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    # Связанные сущности
    players: Mapped[List["Player"]] = relationship(
        "Player",
        back_populates="tournament",
        cascade="all, delete-orphan",
    )
    rounds_list: Mapped[List["Round"]] = relationship(
        "Round",
        back_populates="tournament",
        cascade="all, delete-orphan",
    )

