from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from merge_review.database import get_session
from merge_review.models import User
from merge_review.schemas import LoginRequest, UserRegistration, UserResponse
from merge_review.security import (
    DUMMY_PASSWORD_HASH,
    clear_session_cookie,
    get_current_user,
    hash_password,
    set_session_cookie,
    verify_password,
)

router = APIRouter(prefix="/auth")


def invalid_credentials() -> HTTPException:
    return HTTPException(401, detail="Invalid username or password")


@router.post("/register", response_model=UserResponse, status_code=201)
def register(
    request: UserRegistration,
    response: Response,
    session: Session = Depends(get_session),
) -> User:
    existing = session.scalar(select(User.id).where(User.username == request.username))
    if existing is not None:
        raise HTTPException(409, detail="Username is already registered")
    user = User(
        username=request.username,
        display_name=request.display_name,
        password_hash=hash_password(request.password),
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, detail="Username is already registered") from None
    session.refresh(user)
    set_session_cookie(response, user.id)
    return user


@router.post("/login", response_model=UserResponse)
def login(
    request: LoginRequest,
    response: Response,
    session: Session = Depends(get_session),
) -> User:
    user = session.scalar(select(User).where(User.username == request.username))
    if user is None:
        verify_password(request.password, DUMMY_PASSWORD_HASH)
        raise invalid_credentials()
    if not verify_password(request.password, user.password_hash):
        raise invalid_credentials()
    set_session_cookie(response, user.id)
    return user


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    clear_session_cookie(response)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
