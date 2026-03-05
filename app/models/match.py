from __future__ import annotations

from typing import Optional

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class MatchResult(str):
    """
    Простое перечисление возможных результатов партии.
    Значения храним как строки для простоты.
    """

    WHITE_WIN = "1-0"
    BLACK_WIN = "0-1"
    DRAW = "0.5-0.5"
    BYE = "bye"


class Match(Base):
    """
    Шахматная партия между двумя участниками в конкретном раунде.
    """

    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    round_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("rounds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    board_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    white_player_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
    )
    black_player_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("players.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Строковый результат, плюс числовые очки для удобства подсчёта.
    result: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    white_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    black_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pgn: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    round: Mapped["Round"] = relationship("Round", back_populates="matches")
    white_player: Mapped["Player"] = relationship(
        "Player",
        back_populates="white_matches",
        foreign_keys=[white_player_id],
    )
    black_player: Mapped[Optional["Player"]] = relationship(
        "Player",
        back_populates="black_matches",
        foreign_keys=[black_player_id],
    )

