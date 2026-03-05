from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.auth import get_current_admin, get_current_user_optional
from app.db.session import get_db
from app.models.player import Player
from app.models.user import User
from app.models.tournament import Tournament, TournamentStatus
from app.schemas.tournament import TournamentListItem
from app.services.pdf_export import export_standings_pdf
from app.services.standings import calculate_standings, recalculate_scores


router = APIRouter(prefix="/tournaments", tags=["tournaments"])


def get_templates() -> Jinja2Templates:
    """
    Возвращает экземпляр Jinja2Templates.

    В реальном проекте это можно было бы передавать через зависимости,
    но для учебного проекта достаточно простой фабрики.
    """
    from pathlib import Path

    from fastapi.templating import Jinja2Templates

    base_dir = Path(__file__).resolve().parent.parent.parent
    templates_dir = base_dir / "templates"
    return Jinja2Templates(directory=str(templates_dir))


PAGE_SIZE = 12


@router.get("/", response_class=HTMLResponse)
def list_tournaments(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional["User"] = Depends(get_current_user_optional),
    q: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
) -> HTMLResponse:
    """
    Страница со списком турниров с поиском, фильтром и пагинацией.
    """
    query = db.query(Tournament).order_by(Tournament.id)
    if q and q.strip():
        search = f"%{q.strip()}%"
        query = query.filter(Tournament.name.ilike(search))
    if status and status.strip() in ("planned", "registration", "running", "finished"):
        query = query.filter(Tournament.status == status.strip())

    total = query.count()
    page = max(1, page)
    offset = (page - 1) * PAGE_SIZE
    tournaments: List[Tournament] = query.offset(offset).limit(PAGE_SIZE).all()

    tournaments_view: List[TournamentListItem] = [
        TournamentListItem.model_validate(t) for t in tournaments
    ]
    player_counts = {t.id: len(t.players) for t in tournaments}
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    templates = get_templates()
    is_admin = current_user.is_admin if current_user else False
    return templates.TemplateResponse(
        "tournaments/list.html",
        {
            "request": request,
            "page_title": "Список турниров",
            "tournaments": tournaments_view,
            "player_counts": player_counts,
            "is_admin": is_admin,
            "search_q": (q or "").strip(),
            "filter_status": (status or "").strip(),
            "page": page,
            "total_pages": total_pages,
            "total": total,
        },
    )


@router.get("/register", response_class=HTMLResponse)
def public_register_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> HTMLResponse:
    """
    Публичная страница регистрации участника на турнир.
    Для авторизованных пользователей форма предзаполняется данными из профиля.
    """
    tournaments: List[Tournament] = (
        db.query(Tournament)
        .filter(Tournament.status != TournamentStatus.FINISHED)
        .order_by(Tournament.id)
        .all()
    )

    default_name = ""
    default_rating: Optional[int] = None
    if current_user:
        default_name = (current_user.first_name or "").strip() or current_user.email or ""
        default_rating = current_user.rating_elo

    templates = get_templates()
    return templates.TemplateResponse(
        "tournaments/register.html",
        {
            "request": request,
            "page_title": "Регистрация участника",
            "tournaments": tournaments,
            "default_name": default_name,
            "default_rating": default_rating,
        },
    )


@router.get("/new", response_class=HTMLResponse)
def new_tournament(
    request: Request,
    admin: User = Depends(get_current_admin),
) -> HTMLResponse:
    """
    Форма создания нового турнира.
    """
    templates = get_templates()
    return templates.TemplateResponse(
        "tournaments/create.html",
        {
            "request": request,
            "page_title": "Создание турнира",
        },
    )


@router.post("/new")
def create_tournament(
    request: Request,
    name: str = Form(...),
    rounds: int = Form(...),
    time_control: Optional[str] = Form(None),
    max_players: Optional[int] = Form(None),
    venue: Optional[str] = Form(None),
    prize_fund: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin),
) -> RedirectResponse:
    """
    Обработка отправки формы создания турнира.
    """
    tournament = Tournament(
        name=name.strip(),
        rounds=rounds,
        time_control=(time_control or None),
        max_players=(max_players or None),
        venue=(venue.strip() if venue else None) or None,
        prize_fund=(prize_fund.strip() if prize_fund else None) or None,
    )
    db.add(tournament)
    db.commit()
    db.refresh(tournament)

    url = str(request.url_for("list_tournaments")) + "?flash=created"
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{tournament_id}/edit", response_class=HTMLResponse)
def edit_tournament_page(
    tournament_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> HTMLResponse:
    """Форма редактирования турнира. Только для администратора."""
    tournament: Tournament | None = db.get(Tournament, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Турнир не найден")

    templates = get_templates()
    return templates.TemplateResponse(
        "tournaments/edit.html",
        {
            "request": request,
            "page_title": f"Редактировать: {tournament.name}",
            "tournament": tournament,
        },
    )


@router.post("/{tournament_id}/edit")
def update_tournament(
    tournament_id: int,
    request: Request,
    name: str = Form(...),
    rounds: int = Form(...),
    time_control: Optional[str] = Form(None),
    max_players: Optional[int] = Form(None),
    venue: Optional[str] = Form(None),
    prize_fund: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> RedirectResponse:
    """Сохранение изменений турнира."""
    tournament: Tournament | None = db.get(Tournament, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Турнир не найден")

    tournament.name = name.strip()
    tournament.rounds = rounds
    tournament.time_control = (time_control or None)
    tournament.max_players = (max_players or None)
    tournament.venue = (venue.strip() if venue else None) or None
    tournament.prize_fund = (prize_fund.strip() if prize_fund else None) or None
    db.commit()

    url = str(request.url_for("tournament_detail", tournament_id=tournament.id)) + "?flash=saved"
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{tournament_id}/delete")
def delete_tournament(
    tournament_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> RedirectResponse:
    """
    Удаление турнира. Только для администратора.
    """
    tournament: Tournament | None = db.get(Tournament, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Турнир не найден")
    db.delete(tournament)
    db.commit()
    url = str(request.url_for("list_tournaments")) + "?flash=deleted"
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{tournament_id}", response_class=HTMLResponse)
def tournament_detail(
    tournament_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> HTMLResponse:
    """
    Страница конкретного турнира: общая информация и список участников.
    """
    tournament: Tournament | None = db.get(Tournament, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Турнир не найден")

    # Пересчитываем очки перед показом таблицы участников.
    recalculate_scores(db, tournament)
    standings = (
        calculate_standings(tournament) if tournament.status == "finished" else []
    )

    is_admin = current_user.is_admin if current_user else False
    rounds_list = getattr(tournament, "rounds_list", []) or []
    rounds_sorted = sorted(rounds_list, key=lambda x: x.number)
    rounds_by_number = {r.number: r for r in rounds_sorted}
    current_round_num = next((r.number for r in reversed(rounds_sorted) if not r.is_finished), None)

    player_has_matches = {
        p.id: (len(p.white_matches) + len(p.black_matches)) > 0
        for p in tournament.players
    }

    templates = get_templates()
    return templates.TemplateResponse(
        "tournaments/detail.html",
        {
            "request": request,
            "page_title": f"Турнир: {tournament.name}",
            "tournament": tournament,
            "players": tournament.players,
            "standings": standings,
            "is_admin": is_admin,
            "rounds_by_number": rounds_by_number,
            "current_round_num": current_round_num,
            "player_has_matches": player_has_matches,
        },
    )


@router.get("/{tournament_id}/standings", response_class=HTMLResponse)
def tournament_standings(
    tournament_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """
    Полная турнирная таблица с коэффициентами Buchholz и Median-Buchholz.
    """
    tournament: Tournament | None = db.get(Tournament, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Турнир не найден")

    recalculate_scores(db, tournament)
    standings = calculate_standings(tournament)

    templates = get_templates()
    return templates.TemplateResponse(
        "tournaments/standings.html",
        {
            "request": request,
            "page_title": f"Турнирная таблица — {tournament.name}",
            "tournament": tournament,
            "standings": standings,
        },
    )


@router.get("/{tournament_id}/standings/export/csv")
def export_standings_csv(
    tournament_id: int,
    db: Session = Depends(get_db),
) -> Response:
    """
    Экспорт турнирной таблицы в CSV.
    """
    tournament: Tournament | None = db.get(Tournament, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Турнир не найден")

    recalculate_scores(db, tournament)
    standings = calculate_standings(tournament)

    lines = [
        "place;name;rating;score;buchholz;median_buchholz;color_balance",
    ]
    for idx, row in enumerate(standings, start=1):
        lines.append(
            f'{idx};"{row.player.display_name}";{row.player.rating_elo or ""};'
            f'{row.score};{row.buchholz};{row.median_buchholz};{row.player.color_balance}'
        )

    csv_content = "\n".join(lines)
    filename = f"tournament_{tournament_id}_standings.csv"

    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{tournament_id}/standings/export/pdf")
def export_standings_pdf_route(
    tournament_id: int,
    db: Session = Depends(get_db),
) -> Response:
    """
    Экспорт турнирной таблицы в PDF.
    """
    tournament: Tournament | None = db.get(Tournament, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Турнир не найден")

    recalculate_scores(db, tournament)
    standings = calculate_standings(tournament)
    pdf_bytes = export_standings_pdf(tournament, standings)
    filename = f"tournament_{tournament_id}_standings.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{tournament_id}/players")
def add_player(
    tournament_id: int,
    request: Request,
    full_name: str = Form(...),
    rating_elo: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> RedirectResponse:
    """
    Регистрация участника на турнир.

    Пока без полноценной учётной записи/логина: создаём только сущность Player,
    что достаточно для алгоритма швейцарской системы и турнирной таблицы.
    """
    tournament: Tournament | None = db.query(Tournament).get(tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Турнир не найден")

    # Проверяем ограничение по количеству участников, если оно задано.
    if tournament.max_players is not None and len(tournament.players) >= tournament.max_players:
        raise HTTPException(
            status_code=400,
            detail="Достигнут максимальный лимит участников для этого турнира.",
        )

    player = Player(
        tournament_id=tournament.id,
        display_name=full_name.strip(),
        rating_elo=rating_elo,
    )
    db.add(player)
    db.commit()

    url = str(request.url_for("tournament_detail", tournament_id=tournament.id)) + "?flash=registered"
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{tournament_id}/remove-player")
def remove_player(
    tournament_id: int,
    request: Request,
    player_id: int = Form(...),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> RedirectResponse:
    """
    Удаление участника из турнира. Только для администратора.
    Разрешено только если участник ещё не сыграл ни одной партии.
    """
    tournament: Tournament | None = db.get(Tournament, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Турнир не найден")

    player: Player | None = db.get(Player, player_id)
    if player is None or player.tournament_id != tournament_id:
        raise HTTPException(status_code=404, detail="Участник не найден в этом турнире")

    played = len(player.white_matches) + len(player.black_matches)
    if played > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Нельзя удалить участника: уже сыграно партий — {played}.",
        )

    db.delete(player)
    db.commit()

    url = str(request.url_for("tournament_detail", tournament_id=tournament_id)) + "?flash=removed"
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/register")
def public_register(
    request: Request,
    full_name: str = Form(...),
    rating_elo: Optional[int] = Form(None),
    tournament_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> RedirectResponse:
    """
    Публичная регистрация участника с главной страницы / формы регистрации.
    Если пользователь авторизован, привязываем участника к его учётной записи.
    """
    tournament: Tournament | None = db.get(Tournament, tournament_id)
    if tournament is None:
        raise HTTPException(status_code=404, detail="Турнир не найден")

    if tournament.status == TournamentStatus.FINISHED:
        raise HTTPException(status_code=400, detail="Регистрация в завершённый турнир невозможна.")

    if tournament.max_players is not None and len(tournament.players) >= tournament.max_players:
        raise HTTPException(
            status_code=400,
            detail="Достигнут максимальный лимит участников для этого турнира.",
        )

    player = Player(
        tournament_id=tournament.id,
        display_name=full_name.strip(),
        rating_elo=rating_elo,
        user_id=current_user.id if current_user else None,
    )
    db.add(player)
    db.commit()

    url = str(request.url_for("tournament_detail", tournament_id=tournament.id)) + "?flash=registered"
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)

