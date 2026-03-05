from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
from typing import Optional

from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.core.config import settings


def hash_password(password: str) -> str:
    """
    Возвращает хэш пароля.

    Для учебного проекта достаточно SHA-256, без использования bcrypt,
    чтобы избежать ограничений по длине пароля и лишних зависимостей.
    """
    return sha256(password.encode("utf-8")).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверяет соответствие пароля и его хэша."""
    return hash_password(plain_password) == hashed_password


def _get_serializer() -> URLSafeTimedSerializer:
    # Секрет можно вынести в переменную окружения, для диплома достаточно имени приложения.
    secret_key = settings.app_name + "_secret"
    return URLSafeTimedSerializer(secret_key=secret_key, salt="chess-swiss-session")


def create_session_token(user_id: int, max_age: timedelta | None = None) -> str:
    """
    Создаёт подписанный токен с идентификатором пользователя.

    Args:
        user_id: Идентификатор пользователя.
        max_age: Необязательный срок действия.
    """
    s = _get_serializer()
    return s.dumps({"user_id": user_id})


def decode_session_token(token: str, max_age_seconds: int = 7 * 24 * 3600) -> Optional[int]:
    """
    Декодирует токен сессии и возвращает id пользователя или None.
    """
    s = _get_serializer()
    try:
        data = s.loads(token, max_age=max_age_seconds)
    except BadSignature:
        return None
    user_id = data.get("user_id")
    if not isinstance(user_id, int):
        return None
    return user_id

