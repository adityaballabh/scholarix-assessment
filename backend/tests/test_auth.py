from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from merge_review.api import router
from merge_review.config import Settings
from merge_review.database import get_session
from merge_review.models import Base, User
from pydantic import ValidationError
from merge_review.security import (
    COOKIE_NAME,
    READ_METHODS,
    authenticate_writes,
    get_current_user,
    DUMMY_PASSWORD_HASH,
    create_session_token,
    verify_password,
)
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

USERNAME = "adi.reviewer"
PASSWORD = "correct horse battery staple"


def build_auth_client() -> tuple[TestClient, sessionmaker]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    def test_session():
        with factory() as session:
            yield session

    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[get_session] = test_session
    return TestClient(application), factory


def register(client: TestClient):
    return client.post(
        "/api/auth/register",
        json={
            "username": f"  {USERNAME.upper()}  ",
            "display_name": "  Aditya Reviewer  ",
            "password": PASSWORD,
        },
    )


def test_registration_hashes_password_sets_cookie_and_authenticates() -> None:
    client, factory = build_auth_client()

    anonymous_read = client.get("/api/overview")
    anonymous_write = client.post("/api/queue/rebuild")
    response = register(client)
    current = client.get("/api/auth/me")
    duplicate = register(client)

    assert anonymous_read.status_code == 200
    assert anonymous_write.status_code == 401
    assert response.status_code == 201
    assert set(response.json()) == {"id", "username", "display_name"}
    assert response.json()["username"] == USERNAME
    assert response.json()["display_name"] == "Aditya Reviewer"
    cookie = response.headers["set-cookie"].lower()
    assert f"{COOKIE_NAME}=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "max-age=43200" in cookie
    assert "path=/" in cookie
    assert "secure" not in cookie
    assert current.status_code == 200
    assert current.json() == response.json()
    assert duplicate.status_code == 409

    with factory() as session:
        user = session.scalar(select(User))
    assert user.password_hash != PASSWORD
    assert user.password_hash.startswith("$argon2id$")
    assert verify_password(PASSWORD, user.password_hash)


def test_login_uses_generic_errors_and_logout_expires_session() -> None:
    client, _ = build_auth_client()
    register(client)
    logout = client.post("/api/auth/logout")
    after_logout = client.get("/api/auth/me")

    wrong_password = client.post(
        "/api/auth/login",
        json={"username": USERNAME, "password": "wrong password"},
    )
    with patch("merge_review.api.auth.verify_password", wraps=verify_password) as verify:
        unknown_user = client.post(
            "/api/auth/login",
            json={"username": "missing", "password": "wrong password"},
        )
    login = client.post(
        "/api/auth/login",
        json={"username": USERNAME.upper(), "password": PASSWORD},
    )
    current = client.get("/api/auth/me")
    second_logout = client.post("/api/auth/logout")
    read_after_logout = client.get("/api/activity")
    write_after_logout = client.post("/api/queue/rebuild")

    assert logout.status_code == 204
    assert f"{COOKIE_NAME}=" in logout.headers["set-cookie"].lower()
    assert "max-age=0" in logout.headers["set-cookie"].lower()
    assert after_logout.status_code == 401
    assert wrong_password.status_code == 401
    assert unknown_user.status_code == 401
    assert (
        wrong_password.json() == unknown_user.json() == {"detail": "Invalid username or password"}
    )
    assert verify.call_args.args == ("wrong password", DUMMY_PASSWORD_HASH)
    assert login.status_code == 200
    assert current.status_code == 200
    assert second_logout.status_code == 204
    assert read_after_logout.status_code == 200
    assert write_after_logout.status_code == 401


def test_invalid_expired_and_unknown_user_tokens_are_rejected() -> None:
    client, _ = build_auth_client()
    user_id = uuid4()

    client.cookies.set(COOKIE_NAME, "not-a-jwt")
    invalid = client.get("/api/auth/me")
    client.cookies.set(
        COOKIE_NAME,
        create_session_token(user_id, expires=timedelta(seconds=-1)),
    )
    expired = client.get("/api/auth/me")
    client.cookies.set(COOKIE_NAME, create_session_token(user_id))
    missing_user = client.get("/api/auth/me")

    assert invalid.status_code == 401
    assert expired.status_code == 401
    assert missing_user.status_code == 401
    assert (
        invalid.json()
        == expired.json()
        == missing_user.json()
        == {"detail": "Authentication required"}
    )


def test_registration_validates_account_fields() -> None:
    client, _ = build_auth_client()

    bad_username = client.post(
        "/api/auth/register",
        json={"username": "not allowed", "display_name": "Reviewer", "password": PASSWORD},
    )
    blank_name = client.post(
        "/api/auth/register",
        json={"username": "reviewer", "display_name": "   ", "password": PASSWORD},
    )
    short_password = client.post(
        "/api/auth/register",
        json={"username": "reviewer", "display_name": "Reviewer", "password": "short"},
    )
    long_name = client.post(
        "/api/auth/register",
        json={"username": "reviewer", "display_name": "R" * 65, "password": PASSWORD},
    )

    assert bad_username.status_code == 422
    assert blank_name.status_code == 422
    assert short_password.status_code == 422
    assert long_name.status_code == 422


def test_production_requires_a_configured_auth_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="production", _env_file=None)

    configured = Settings(
        environment="production",
        auth_secret="a-real-deployment-secret-of-sufficient-length",
        _env_file=None,
    )

    assert configured.auth_secret == "a-real-deployment-secret-of-sufficient-length"


def test_a_deployed_cookie_is_secure_and_cross_site() -> None:
    client, _ = build_auth_client()
    production = Settings(
        environment="production",
        auth_secret="a-real-deployment-secret-of-sufficient-length",
        _env_file=None,
    )

    with patch("merge_review.security.get_settings", return_value=production):
        response = register(client)

    cookie = response.headers["set-cookie"].lower()

    assert response.status_code == 201
    assert "samesite=none" in cookie
    assert "secure" in cookie
    assert "httponly" in cookie


def test_every_write_route_requires_a_signed_in_reviewer() -> None:
    client, _ = build_auth_client()
    placeholders = {
        "fetch_id": str(uuid4()),
        "case_id": "case-one",
        "author_slug": "Dummy_Author",
        "source": "openalex",
        "doi": "10.123/dummy",
    }

    responses = {}
    for path, operations in client.app.openapi()["paths"].items():
        if path.startswith("/api/auth"):
            continue
        url = path
        for name, value in placeholders.items():
            url = url.replace(f"{{{name}}}", value).replace(f"{{{name}:path}}", value)
        for method in operations:
            if method.upper() in READ_METHODS:
                continue
            responses[f"{method.upper()} {path}"] = client.request(
                method.upper(), url, json={}
            ).status_code

    assert len(responses) >= 8
    assert {route: status for route, status in responses.items() if status != 401} == {}
