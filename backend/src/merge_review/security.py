from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, Response
from fastapi.security import APIKeyCookie
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from merge_review.config import get_settings
from merge_review.database import get_session
from merge_review.models import User

ALGORITHM = "HS256"
COOKIE_NAME = "merge_review_session"
READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
password_hash = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hash.hash("merge-review-dummy-password")
session_cookie = APIKeyCookie(name=COOKIE_NAME, auto_error=False)


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_session_token(
    user_id: UUID,
    expires: timedelta | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    expires = expires or timedelta(hours=settings.auth_token_hours)
    return jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": now + expires},
        settings.auth_secret,
        algorithm=ALGORITHM,
    )


def set_session_cookie(response: Response, user_id: UUID) -> None:
    settings = get_settings()
    max_age = settings.auth_token_hours * 60 * 60
    # A cross-site cookie needs SameSite=None, allowed only alongside Secure
    cross_site = settings.frontend_hosting == "separate_origin"
    response.set_cookie(
        key=COOKIE_NAME,
        value=create_session_token(user_id),
        max_age=max_age,
        path="/",
        secure=cross_site,
        httponly=True,
        samesite="none" if cross_site else "lax",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def authentication_error() -> HTTPException:
    return HTTPException(401, detail="Authentication required")


def reject_foreign_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin is not None and origin != get_settings().frontend_origin:
        raise HTTPException(403, detail="Cross-site request rejected")


def get_current_user(
    token: str | None = Depends(session_cookie),
    session: Session = Depends(get_session),
) -> User:
    return resolve_user(token, session)


def authenticate_writes(
    request: Request,
    token: str | None = Depends(session_cookie),
    session: Session = Depends(get_session),
) -> User | None:
    """Reading the queue is open; anything that changes state needs a signed-in reviewer."""
    if request.method in READ_METHODS:
        return None
    reject_foreign_origin(request)
    return resolve_user(token, session)


def resolve_user(token: str | None, session: Session) -> User:
    if token is None:
        raise authentication_error()
    try:
        payload = jwt.decode(
            token,
            get_settings().auth_secret,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
        user_id = UUID(payload["sub"])
    except (InvalidTokenError, KeyError, TypeError, ValueError):
        raise authentication_error() from None
    user = session.get(User, user_id)
    if user is None:
        raise authentication_error()
    return user
