from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_admin, get_current_user_optional
from app.db.session import get_db
from app.models.player import Player
from app.models.user import User
from app.models.round import Round
from app.models.tournament import Tournament
from app.services.standings import recalculate_scores
from app.services.swiss_pairing import Pairing, generate_swiss_pairings


router = APIRouter(prefix="/tournaments", tags=["rounds"])


def get_templates() -> Jinja2Templates:
    from pathlib import Path

    from fastapi.templating import Jinja2Templates

    base_dir = Path(__file__).resolve().parent.parent.parent
    templates_dir = base_dir / "templates"
    return Jinja2Templates(directory=str(templates_dir))


def _get_tournament_or_404(db: Session, tournament_id: int) -> Tournament:
    tournament: Tournament | None = db.get(Tournament, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Турнир не найден")
    return tournament


@router.post("/{tournament_id}/rounds/start")
def start_next_round(
    tournament_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> RedirectResponse:
    """
    Генерирует следующий тур по швейцарской системе и создаёт пары (Match).
    """
    tournament = _get_tournament_or_404(db, tournament_id)

    # Определяем номер следующего тура.
    existing_rounds: List[Round] = (
        db.execute(
            select(Round)
            .where(Round.tournament_id == tournament.id)
            .order_by(Round.number)
        )
        .scalars()
        .all()
    )
    next_number = len(existing_rounds) + 1

    if next_number > tournament.rounds:
        # Все туры уже сыграны — просто возвращаем пользователя на страницу турнира.
        return RedirectResponse(
            url=request.url_for("tournament_detail", tournament_id=tournament.id),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Пересчитываем очки перед жеребьёвкой.
    recalculate_scores(db, tournament)

    players: List[Player] = (
        db.execute(
            select(Player)
            .where(Player.tournament_id == tournament.id, Player.is_active.is_(True))
            .order_by(Player.id)
        )
        .scalars()
        .all()
    )

    if len(players) < 2:
        raise HTTPException(
            status_code=400,
            detail="Для начала тура нужно минимум два участника.",
        )

    # Создаём объект тура.
    round_obj = Round(
        tournament_id=tournament.id,
        number=next_number,
        started_at=datetime.utcnow(),
        is_finished=False,
    )
    db.add(round_obj)
    db.flush()  # чтобы у тура появился id

    # Турнир считается начавшимся.
    from app.models.tournament import TournamentStatus

    if tournament.status == TournamentStatus.PLANNED:
        tournament.status = TournamentStatus.RUNNING

    # Генерируем пары.
    pairings: List[Pairing] = generate_swiss_pairings(
        tournament=tournament,
        players=players,
        previous_rounds=existing_rounds,
    )

    from app.models.match import Match, MatchResult

    board_number = 1
    for pairing in pairings:
        if pairing.black_player is None:
            # Бай: участник получает 1 очко без соперника.
            match = Match(
                round_id=round_obj.id,
                board_number=board_number,
                white_player_id=pairing.white_player.id,
                black_player_id=None,
                result=MatchResult.BYE,
                white_score=1.0,
                black_score=None,
            )
        else:
            match = Match(
                round_id=round_obj.id,
                board_number=board_number,
                white_player_id=pairing.white_player.id,
                black_player_id=pairing.black_player.id,
                result=None,
                white_score=None,
                black_score=None,
            )
        db.add(match)
        board_number += 1

    db.commit()

    url = str(request.url_for("current_round", tournament_id=tournament.id)) + "?flash=round_started"
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{tournament_id}/rounds/current", response_class=HTMLResponse)
def current_round(
    tournament_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> HTMLResponse:
    """
    Страница текущего (последнего созданного) тура.
    """
    tournament = _get_tournament_or_404(db, tournament_id)

    round_obj: Round | None = (
        db.execute(
            select(Round)
            .where(Round.tournament_id == tournament.id)
            .order_by(Round.number.desc())
        )
        .scalars()
        .first()
    )
    if round_obj is None:
        raise HTTPException(status_code=404, detail="Для турнира ещё не создано ни одного тура.")

    is_admin = current_user.is_admin if current_user else False
    templates = get_templates()
    return templates.TemplateResponse(
        "rounds/current.html",
        {
            "request": request,
            "page_title": f"Текущий тур — {tournament.name}",
            "tournament": tournament,
            "round": round_obj,
            "matches": round_obj.matches,
            "is_admin": is_admin,
        },
    )


@router.get("/{tournament_id}/rounds", response_class=HTMLResponse)
def rounds_history(
    tournament_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """
    История всех туров и сыгранных партий турнира.
    """
    tournament = _get_tournament_or_404(db, tournament_id)

    rounds: List[Round] = (
        db.execute(
            select(Round)
            .where(Round.tournament_id == tournament.id)
            .order_by(Round.number)
        )
        .scalars()
        .all()
    )

    templates = get_templates()
    return templates.TemplateResponse(
        "rounds/list.html",
        {
            "request": request,
            "page_title": f"Туры — {tournament.name}",
            "tournament": tournament,
            "rounds": rounds,
        },
    )

