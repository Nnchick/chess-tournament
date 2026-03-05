"""
Экспорт турнирной таблицы в PDF.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

if TYPE_CHECKING:
    from app.models.tournament import Tournament
    from app.services.standings import PlayerStanding


def _get_cyrillic_font_path() -> Optional[Path]:
    """Путь к шрифту с поддержкой кириллицы."""
    candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/times.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _ensure_cyrillic_font() -> str:
    """Регистрирует и возвращает имя шрифта для кириллицы."""
    font_name = "CyrillicFont"
    try:
        pdfmetrics.getFont(font_name)
        return font_name
    except (KeyError, TypeError):
        pass
    path = _get_cyrillic_font_path()
    if path:
        pdfmetrics.registerFont(TTFont(font_name, str(path)))
        return font_name
    return "Helvetica"


def export_standings_pdf(
    tournament: "Tournament",
    standings: List["PlayerStanding"],
) -> bytes:
    """
    Формирует PDF с турнирной таблицей.
    """
    buffer = BytesIO()
    font_name = _ensure_cyrillic_font()
    styles = getSampleStyleSheet()
    styles["Normal"].fontName = font_name

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    data = [
        ["Место", "Участник", "Рейтинг", "Очки", "Buchholz", "Median-B.", "Цв.баланс"],
    ]
    for idx, row in enumerate(standings, start=1):
        data.append([
            str(idx),
            _esc(row.player.display_name),
            str(row.player.rating_elo) if row.player.rating_elo else "—",
            f"{row.score:.1f}",
            f"{row.buchholz:.1f}",
            f"{row.median_buchholz:.1f}",
            str(row.player.color_balance),
        ])

    table = Table(data)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d3748")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 0), (1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fafc")]),
    ]))

    style_title = getSampleStyleSheet()["Normal"]
    style_title.fontName = font_name
    style_title.fontSize = 14
    title_para = Paragraph(
        f"<b>Турнирная таблица — {_esc(tournament.name)}</b>",
        style_title,
    )
    sub_para = Paragraph(
        f"Туров: {tournament.rounds}, контроль: {_esc(tournament.time_control or '—')}",
        styles["Normal"],
    )
    doc.build([title_para, sub_para, table])
    return buffer.getvalue()


def _esc(s: str) -> str:
    """Экранирует HTML-символы для ReportLab Paragraph."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
