from __future__ import annotations

from datetime import datetime
from typing import List

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Round(Base):
    """
    Раунд (тур) в рамках турнира.
    """

    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    tournament_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tournaments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    number: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_finished: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    tournament: Mapped["Tournament"] = relationship(
        "Tournament", back_populates="rounds_list"
    )
    matches: Mapped[List["Match"]] = relationship(
        "Match",
        back_populates="round",
        cascade="all, delete-orphan",
    )

