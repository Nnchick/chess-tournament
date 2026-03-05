from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.auth import get_current_admin, get_current_user_optional
from app.db.session import get_db
from app.models.match import Match, MatchResult
from app.models.user import User
from app.models.tournament import TournamentStatus
from app.services.standings import recalculate_scores


router = APIRouter(prefix="/matches", tags=["matches"])


def get_templates() -> Jinja2Templates:
    from pathlib import Path

    base_dir = Path(__file__).resolve().parent.parent.parent
    templates_dir = base_dir / "templates"
    return Jinja2Templates(directory=str(templates_dir))


@router.get("/{match_id}", response_class=HTMLResponse)
def match_detail(
    match_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> HTMLResponse:
    """
    Страница отдельной партии с текстовой нотацией.
    """
    match: Match | None = db.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Партия не найдена")

    is_admin = current_user.is_admin if current_user else False
    templates = get_templates()
    return templates.TemplateResponse(
        "matches/detail.html",
        {
            "request": request,
            "page_title": "Просмотр партии",
            "match": match,
            "is_admin": is_admin,
        },
    )


@router.get("/{match_id}/pgn/download")
def download_match_pgn(
    match_id: int,
    db: Session = Depends(get_db),
) -> Response:
    """Скачать PGN партии как файл."""
    match: Match | None = db.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Партия не найдена")

    pgn = match.pgn or ""
    filename = f"game_{match_id}.pgn"
    return Response(
        content=pgn.encode("utf-8"),
        media_type="application/x-chess-pgn; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{match_id}/result")
def update_match_result(
    match_id: int,
    request: Request,
    result: str = Form(...),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> RedirectResponse:
    """
    Ввод результата партии.

    Возможные значения result:
    - "1-0" — победа белых;
    - "0-1" — победа чёрных;
    - "0.5-0.5" — ничья.
    """
    match: Match | None = db.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Партия не найдена")

    if match.result == MatchResult.BYE:
        raise HTTPException(status_code=400, detail="Нельзя изменить результат byе-партии.")

    if result not in {MatchResult.WHITE_WIN, MatchResult.BLACK_WIN, MatchResult.DRAW}:
        raise HTTPException(status_code=400, detail="Некорректный результат.")

    match.result = result
    if result == MatchResult.WHITE_WIN:
        match.white_score = 1.0
        match.black_score = 0.0
    elif result == MatchResult.BLACK_WIN:
        match.white_score = 0.0
        match.black_score = 1.0
    else:
        match.white_score = 0.5
        match.black_score = 0.5

    tournament = match.round.tournament
    recalculate_scores(db, tournament)
    _maybe_finish_tournament(tournament)
    db.commit()

    url = str(request.url_for("current_round", tournament_id=tournament.id)) + "?flash=results_saved"
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/bulk-results")
def update_matches_bulk(
    request: Request,
    match_id: List[int] = Form([]),
    result: List[str] = Form([]),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> RedirectResponse:
    """
    Массовое сохранение результатов нескольких партий.

    Данные приходят парами (match_id, result). Пустые результаты игнорируются.
    """
    if not match_id or not result:
        return RedirectResponse(
            url=request.headers.get("referer") or request.url_for("index"),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    from itertools import zip_longest

    tournament = None

    for m_id, res in zip_longest(match_id, result, fillvalue=""):
        if not m_id or not res:
            continue
        match: Match | None = db.get(Match, int(m_id))
        if match is None or match.result == MatchResult.BYE:
            continue
        if res not in {MatchResult.WHITE_WIN, MatchResult.BLACK_WIN, MatchResult.DRAW}:
            continue

        match.result = res
        if res == MatchResult.WHITE_WIN:
            match.white_score = 1.0
            match.black_score = 0.0
        elif res == MatchResult.BLACK_WIN:
            match.white_score = 0.0
            match.black_score = 1.0
        else:
            match.white_score = 0.5
            match.black_score = 0.5

        if tournament is None:
            tournament = match.round.tournament

    if tournament is not None:
        recalculate_scores(db, tournament)
        _maybe_finish_tournament(tournament)
    db.commit()

    if tournament is not None:
        redirect_url = str(request.url_for("current_round", tournament_id=tournament.id)) + "?flash=results_saved"
    else:
        redirect_url = request.headers.get("referer") or request.url_for("index")

    return RedirectResponse(
        url=redirect_url,
        status_code=status.HTTP_303_SEE_OTHER,
    )

@router.post("/{match_id}/pgn")
def update_match_pgn(
    match_id: int,
    request: Request,
    pgn: str = Form(""),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> RedirectResponse:
    """
    Обновление текстовой нотации (PGN) для партии.
    """
    match: Match | None = db.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Партия не найдена")

    match.pgn = pgn.strip() or None
    db.commit()

    url = str(request.url_for("match_detail", match_id=match.id)) + "?flash=saved"
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


def _maybe_finish_tournament(tournament) -> None:
    """
    Помечает турнир как завершённый, если сыграно нужное количество туров
    и во всех партиях есть результат (кроме bye).
    """
    if tournament.status == TournamentStatus.FINISHED:
        return

    rounds = getattr(tournament, "rounds_list", []) or []
    if len(rounds) < tournament.rounds:
        return

    for round_ in rounds:
        for match in round_.matches:
            if match.result in (None, ""):
                return

    tournament.status = TournamentStatus.FINISHED

