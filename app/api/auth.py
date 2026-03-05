from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.security import create_session_token, hash_password, verify_password
from app.db.session import SessionLocal, get_db
from app.models.player import Player
from app.models.user import User


router = APIRouter(prefix="/auth", tags=["auth"])


def get_templates() -> Jinja2Templates:
    from pathlib import Path

    from fastapi.templating import Jinja2Templates

    base_dir = Path(__file__).resolve().parent.parent.parent
    templates_dir = base_dir / "templates"
    return Jinja2Templates(directory=str(templates_dir))


def get_current_user(db: Session, request: Request) -> Optional[User]:
    """
    Возвращает текущего пользователя на основе куки session.
    """
    token = request.cookies.get("session")
    if not token:
        return None

    from app.core.security import decode_session_token

    user_id = decode_session_token(token)
    if user_id is None:
        return None
    return db.get(User, user_id)


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    Возвращает текущего пользователя или None, если не авторизован.
    """
    return get_current_user(db, request)


def get_current_admin(db: Session = Depends(get_db), request: Request = None) -> User:
    """
    Зависимость для маршрутов, доступных только администратору.
    """
    assert request is not None  # для mypy
    user = get_current_user(db, request)
    if user is None or not user.is_admin:
        raise HTTPException(status_code=403, detail="Требуется вход как администратор.")
    return user


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request) -> HTMLResponse:
    templates = get_templates()
    return templates.TemplateResponse(
        "auth/register.html",
        {
            "request": request,
            "page_title": "Регистрация",
            "error": None,
        },
    )


@router.post("/register", response_model=None)
def register(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    first_name: str | None = Form(None),
    db: Session = Depends(get_db),
):
    templates = get_templates()
    error = None
    if password != password_confirm:
        error = "Пароли не совпадают."
    elif len(password) < 6:
        error = "Пароль должен быть не менее 6 символов."
    else:
        email_normalized = email.strip().lower()
        existing = db.query(User).filter(User.email == email_normalized).first()
        if existing:
            error = "Пользователь с таким email уже зарегистрирован."
        else:
            user = User(
                email=email_normalized,
                hashed_password=hash_password(password),
                first_name=(first_name.strip() if first_name else None) or None,
                is_admin=False,
                is_active=True,
            )
            db.add(user)
            db.commit()
            token = create_session_token(user.id)
            redirect_resp = RedirectResponse(
                url=request.url_for("list_tournaments"),
                status_code=status.HTTP_303_SEE_OTHER,
            )
            redirect_resp.set_cookie(
                "session",
                value=token,
                httponly=True,
                max_age=7 * 24 * 3600,
                path="/",
            )
            return redirect_resp

    return templates.TemplateResponse(
        "auth/register.html",
        {
            "request": request,
            "page_title": "Регистрация",
            "error": error,
        },
        status_code=status.HTTP_400_BAD_REQUEST,
    )


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    templates = get_templates()
    return templates.TemplateResponse(
        "auth/login.html",
        {
            "request": request,
            "page_title": "Вход",
            "error": None,
        },
    )


@router.post("/login")
def login(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """
    Обработка формы входа.
    """
    email_normalized = email.strip().lower()
    user: Optional[User] = (
        db.query(User).filter(User.email == email_normalized, User.is_active.is_(True)).first()
    )
    if user is None or not verify_password(password, user.hashed_password):
        templates = get_templates()
        return templates.TemplateResponse(
            "auth/login.html",
            {
                "request": request,
                "page_title": "Вход",
                "error": "Неверный email или пароль.",
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    token = create_session_token(user.id)
    redirect = RedirectResponse(
        url=request.url_for("list_tournaments"),
        status_code=status.HTTP_303_SEE_OTHER,
    )
    redirect.set_cookie(
        "session",
        value=token,
        httponly=True,
        max_age=7 * 24 * 3600,
        path="/",
    )
    return redirect


@router.get("/profile", response_class=HTMLResponse)
def profile_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> HTMLResponse:
    """
    Профиль участника — турниры, в которых он зарегистрирован.
    """
    if current_user is None:
        raise HTTPException(status_code=401, detail="Войдите, чтобы просмотреть профиль.")

    players: List[Player] = (
        db.query(Player)
        .filter(Player.user_id == current_user.id)
        .order_by(Player.id.desc())
        .all()
    )
    # Собираем турниры с данными участника (место, очки)
    from app.services.standings import calculate_standings, recalculate_scores

    my_tournaments = []
    for p in players:
        t = p.tournament
        recalculate_scores(db, t)
        standings = calculate_standings(t)
        place = next((i for i, s in enumerate(standings, 1) if s.player.id == p.id), None)
        score = p.score
        my_tournaments.append({
            "tournament": t,
            "player": p,
            "place": place,
            "score": score,
            "status": t.status,
        })

    templates = get_templates()
    return templates.TemplateResponse(
        "auth/profile.html",
        {
            "request": request,
            "page_title": "Мои турниры",
            "current_user": current_user,
            "my_tournaments": my_tournaments,
        },
    )


@router.get("/profile/edit", response_class=HTMLResponse)
def profile_edit_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> HTMLResponse:
    """Форма редактирования профиля."""
    if current_user is None:
        raise HTTPException(status_code=401, detail="Войдите, чтобы редактировать профиль.")

    templates = get_templates()
    return templates.TemplateResponse(
        "auth/profile_edit.html",
        {
            "request": request,
            "page_title": "Редактирование профиля",
            "current_user": current_user,
        },
    )


@router.post("/profile/edit")
def profile_update(
    request: Request,
    first_name: Optional[str] = Form(None),
    last_name: Optional[str] = Form(None),
    nickname: Optional[str] = Form(None),
    rating_elo: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
) -> RedirectResponse:
    """Сохранение изменений профиля."""
    if current_user is None:
        raise HTTPException(status_code=401, detail="Войдите, чтобы редактировать профиль.")

    current_user.first_name = (first_name or "").strip() or None
    current_user.last_name = (last_name or "").strip() or None
    current_user.nickname = (nickname or "").strip() or None
    current_user.rating_elo = rating_elo
    db.commit()

    url = str(request.url_for("profile_page")) + "?flash=profile_saved"
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
def logout(request: Request) -> RedirectResponse:
    """
    Выход: очищает куку сессии.
    """
    redirect = RedirectResponse(
        url=request.url_for("index"),
        status_code=status.HTTP_303_SEE_OTHER,
    )
    redirect.delete_cookie("session", path="/")
    return redirect


def ensure_default_admin() -> None:
    """
    Создаёт учётную запись администратора по умолчанию, если её ещё нет.

    Для учебного проекта:
        email: admin@example.com
        пароль: 25252626
    """
    db: Session = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == "admin@example.com").first()
        if admin:
            admin.hashed_password = hash_password("25252626")
            db.commit()
            return
        admin = User(
            email="admin@example.com",
            hashed_password=hash_password("25252626"),
            first_name="Admin",
            is_admin=True,
            is_active=True,
        )
        db.add(admin)
        db.commit()
    finally:
        db.close()

