from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.auth import ensure_default_admin
from app.api.auth import get_current_user as auth_get_current_user
from app.api.auth import router as auth_router
from app.api.matches import router as matches_router
from app.api.rounds import router as rounds_router
from app.api.tournaments import router as tournaments_router
from app.core.config import settings
from app.db.migrations import run_simple_migrations
from app.db.session import Base, engine, get_db


BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application instance.

    Returns:
        FastAPI: Configured application.
    """
    app = FastAPI(title=settings.app_name)

    # Static files and templates
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    # Создаём таблицы при старте приложения (для учебного проекта можно без Alembic).
    Base.metadata.create_all(bind=engine)
    # Простые миграции (например, добавление новых колонок в SQLite).
    run_simple_migrations(engine)
    # Обеспечиваем наличие администратора по умолчанию.
    ensure_default_admin()

    # Обработчик 404
    from starlette.exceptions import HTTPException as StarletteHTTPException

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return templates.TemplateResponse(
                "errors/404.html",
                {"request": request, "page_title": "Страница не найдена"},
                status_code=404,
            )
        raise exc

    # Подключаем роуты
    app.include_router(auth_router)
    app.include_router(tournaments_router)
    app.include_router(rounds_router)
    app.include_router(matches_router)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
        """
        Главная страница приложения с дашбордом статистики.
        """
        from sqlalchemy import func
        from app.models.match import Match
        from app.models.player import Player
        from app.models.tournament import Tournament

        stats = {
            "tournaments": db.query(func.count(Tournament.id)).scalar() or 0,
            "players": db.query(func.count(Player.id)).scalar() or 0,
            "matches": db.query(func.count(Match.id)).scalar() or 0,
        }
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "page_title": "Шахматный турнир по швейцарской системе",
                "stats": stats,
            },
        )

    return app


app = create_app()

