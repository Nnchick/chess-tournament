from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence

from sqlalchemy.orm import Session

from app.models.match import Match
from app.models.player import Player
from app.models.tournament import Tournament


@dataclass
class PlayerStanding:
    """Расчётные показатели игрока для турнирной таблицы."""

    player: Player
    score: float
    buchholz: float
    median_buchholz: float


def recalculate_scores(db: Session, tournament: Tournament) -> None:
    """
    Пересчитывает очки и баланс цвета для всех участников турнира.

    Логика:
    - сбрасываем score и color_balance для всех игроков турнира;
    - проходим по всем партиям всех раундов турнира;
    - добавляем очки и обновляем баланс цвета:
      - белые: +white_score и +1 к балансу, если партия засчитана;
      - чёрные: +black_score и -1 к балансу.
    """
    # Сбрасываем накопленные значения.
    for player in tournament.players:
        player.score = 0.0
        player.color_balance = 0

    for round_ in tournament.rounds_list:
        for match in round_.matches:
            _apply_match_to_scores(match)

    db.flush()


def _apply_match_to_scores(match: Match) -> None:
    """Применяет результат одной партии к игрокам."""
    white: Player | None = match.white_player
    black: Player | None = match.black_player

    if white is not None and match.white_score is not None:
        white.score += float(match.white_score)
        white.color_balance += 1

    if black is not None and match.black_score is not None:
        black.score += float(match.black_score)
        black.color_balance -= 1


def calculate_standings(tournament: Tournament) -> List[PlayerStanding]:
    """
    Строит список турнирной таблицы с дополнительными коэффициентами.

    - Buchholz: сумма очков всех соперников игрока;
    - Median-Buchholz: Buchholz без одного самого сильного и одного самого слабого результата
      (если сыграно меньше 3 партий, используется обычный Buchholz).
    """
    players: List[Player] = list(tournament.players)

    # Карта игрок -> список очков соперников.
    opponents_scores: Dict[int, List[float]] = {p.id: [] for p in players}

    for round_ in tournament.rounds_list:
        for match in round_.matches:
            if match.white_player is None or match.black_player is None:
                continue
            w = match.white_player
            b = match.black_player
            opponents_scores[w.id].append(float(b.score))
            opponents_scores[b.id].append(float(w.score))

    standings: List[PlayerStanding] = []

    for p in players:
        opp_scores = sorted(opponents_scores.get(p.id, []))
        buchholz = float(sum(opp_scores))
        if len(opp_scores) >= 3:
            trimmed = opp_scores[1:-1]  # убираем максимум и минимум
            median_buchholz = float(sum(trimmed))
        else:
            median_buchholz = buchholz

        standings.append(
            PlayerStanding(
                player=p,
                score=float(p.score),
                buchholz=buchholz,
                median_buchholz=median_buchholz,
            )
        )

    # Сортируем по очкам, затем по Median-Buchholz и Buchholz.
    standings.sort(
        key=lambda s: (s.score, s.median_buchholz, s.buchholz, s.player.rating_elo or 0),
        reverse=True,
    )

    return standings

