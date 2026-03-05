from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Set

from app.models.player import Player
from app.models.round import Round
from app.models.tournament import Tournament


@dataclass(frozen=True)
class Pairing:
    """
    Пара игроков в туре.

    Для хранения информации о цветах используем явные ссылки на white/black.
    Если второй игрок отсутствует (бай), black_player будет None.
    """

    white_player: Player
    black_player: Player | None


def generate_swiss_pairings(
    tournament: Tournament,
    players: Sequence[Player],
    previous_rounds: Sequence[Round],
) -> List[Pairing]:
    """
    Упрощённый каркас алгоритма швейцарской системы.

    Реализуем базовый вариант:
    - сортировка по количеству очков (score) по убыванию;
    - по возможности участники с одинаковыми очками играют между собой;
    - при нечётном количестве участников один получает bye (1 очко автоматически);
    - не допускаются повторные встречи (позже добавим учёт истории и цветов).

    Алгоритм (упрощённый, но пригодный для диплома):
    - сортируем активных игроков по очкам и рейтингу;
    - по возможности не допускаем повторных встреч (учитываем историю партий);
    - формируем пары из ближайших по очкам соперников;
    - при нечётном количестве участников один игрок получает bye (1 очко),
      если ранее ещё не получал bye.
    """
    # TODO: в следующих итерациях учесть историю встреч и баланс цвета.

    # Фильтруем только активных игроков.
    active_players: List[Player] = [p for p in players if p.is_active]

    # Сортировка по очкам (score), затем по рейтингу (rating_elo) по убыванию.
    active_players.sort(
        key=lambda p: (p.score, p.rating_elo or 0),
        reverse=True,
    )

    previous_opponents = _build_previous_opponents(previous_rounds)
    players_with_bye: Set[int] = _players_with_bye(previous_rounds)

    pairings: List[Pairing] = []
    unpaired: List[Player] = list(active_players)

    while len(unpaired) > 1:
        player = unpaired.pop(0)
        opponent_index = _find_best_opponent_index(player, unpaired, previous_opponents)
        if opponent_index is None:
            # Не нашли никого, с кем ещё не играл — берём ближайшего по списку.
            opponent = unpaired.pop(0)
        else:
            opponent = unpaired.pop(opponent_index)

        # Простое распределение цветов: у кого хуже баланс цвета, тот получает «любимый» цвет.
        if player.color_balance > opponent.color_balance:
            white, black = opponent, player
        else:
            white, black = player, opponent

        pairings.append(Pairing(white_player=white, black_player=black))

    # Если остался один игрок — назначаем bye.
    if len(unpaired) == 1:
        candidate = unpaired[0]
        if candidate.id in players_with_bye:
            # Ищем игрока без bye среди уже спаренных, у кого минимальный счёт.
            reassigned = _find_candidate_for_bye(pairings, players_with_bye)
            if reassigned is not None:
                # Меняем одно из существующих pairings: reassigned получает bye,
                # его соперник играет с последним оставшимся игроком.
                pairing_idx, old_white, old_black = reassigned
                last_player = candidate

                # Выбираем нового соперника для last_player.
                other = old_black if old_white.id == reassigned[1].id else old_white
                pairings[pairing_idx] = Pairing(white_player=last_player, black_player=other)
                pairings.append(Pairing(white_player=reassigned[1], black_player=None))
            else:
                pairings.append(Pairing(white_player=candidate, black_player=None))
        else:
            pairings.append(Pairing(white_player=candidate, black_player=None))

    return pairings


def _build_previous_opponents(previous_rounds: Sequence[Round]) -> dict[int, Set[int]]:
    result: dict[int, Set[int]] = {}
    for round_ in previous_rounds:
        for match in round_.matches:
            if match.white_player_id is None or match.black_player_id is None:
                continue
            a = match.white_player_id
            b = match.black_player_id
            result.setdefault(a, set()).add(b)
            result.setdefault(b, set()).add(a)
    return result


def _players_with_bye(previous_rounds: Sequence[Round]) -> Set[int]:
    from app.models.match import MatchResult

    players: Set[int] = set()
    for round_ in previous_rounds:
        for match in round_.matches:
            if match.result == MatchResult.BYE and match.white_player_id is not None:
                players.add(match.white_player_id)
    return players


def _find_best_opponent_index(
    player: Player,
    candidates: Sequence[Player],
    previous_opponents: dict[int, Set[int]],
) -> int | None:
    """
    Ищет подходящего соперника среди кандидатов:
    - с ним ещё не играли;
    - максимально близкого по очкам.
    Возвращает индекс в списке candidates или None.
    """
    already_played: Set[int] = previous_opponents.get(player.id, set())
    best_index: int | None = None
    best_diff: float | None = None

    for idx, candidate in enumerate(candidates):
        if candidate.id in already_played:
            continue
        diff = abs(float(player.score) - float(candidate.score))
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_index = idx

    return best_index


def _find_candidate_for_bye(
    pairings: Sequence[Pairing],
    players_with_bye: Set[int],
) -> tuple[int, Player, Player] | None:
    """
    Ищет среди уже сформированных пар игрока без bye
    с минимальным количеством очков, которому можно выдать bye.

    Возвращает кортеж (index_pairing, выбранный_игрок, его_соперник).
    """
    best: tuple[int, Player, Player] | None = None

    for idx, pairing in enumerate(pairings):
        for a, b in ((pairing.white_player, pairing.black_player),):
            if b is None:
                continue
            for candidate, other in ((a, b), (b, a)):
                if candidate.id in players_with_bye:
                    continue
                if best is None or candidate.score < best[1].score:
                    best = (idx, candidate, other)

    return best


