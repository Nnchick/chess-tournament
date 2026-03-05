from __future__ import annotations

from typing import List, Optional

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Player(Base):
    """
    Участник конкретного турнира.

    Отдельная сущность, связывающая пользователя с турниром.
    Это позволяет одному пользователю участвовать в нескольких турнирах.
    """

    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    tournament_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tournaments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # В кэше можем хранить ФИО и рейтинг на момент турнира
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    rating_elo: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Баланс цвета: количество партий белыми минус количество партий чёрными
    color_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    user: Mapped[Optional["User"]] = relationship("User", back_populates="players")
    tournament: Mapped["Tournament"] = relationship(
        "Tournament", back_populates="players"
    )

    white_matches: Mapped[List["Match"]] = relationship(
        "Match",
        back_populates="white_player",
        foreign_keys="Match.white_player_id",
    )
    black_matches: Mapped[List["Match"]] = relationship(
        "Match",
        back_populates="black_player",
        foreign_keys="Match.black_player_id",
    )

