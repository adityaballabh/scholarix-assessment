import pytest
from fastapi.testclient import TestClient
from merge_review.config import get_settings
from merge_review.main import app


@pytest.mark.parametrize(
    "host",
    ["localhost", "localhost:8080", "localhost:5173", "127.0.0.1", "127.0.0.1:8000"],
)
def test_local_hosts_are_allowed(host: str) -> None:
    client = TestClient(app)

    response = client.get("/openapi.json", headers={"Host": host})

    assert response.status_code == 200


@pytest.mark.parametrize(
    "host",
    [
        "untrusted.example:8080",
        "localhost.untrusted.example",
        "untrusted.localhost",
        "127.0.0.1.untrusted.example",
        "untrusted.example@localhost",
        "localhost/path",
        "www.localhost",
        "[::1]",
        "[::1]:8080",
        "[2001:db8::1]:8080",
        "",
    ],
)
def test_unexpected_and_malformed_hosts_are_rejected(host: str) -> None:
    client = TestClient(app)

    response = client.get("/openapi.json", headers={"Host": host})

    assert response.status_code == 400


@pytest.mark.parametrize("path", ["/api/cases", "/api/activity", "/api/export"])
def test_public_reads_reject_unexpected_hosts_before_reaching_the_database(path: str) -> None:
    client = TestClient(app)

    response = client.get(path, headers={"Host": "untrusted.example:8080"})

    assert response.status_code == 400


def test_missing_host_header_is_rejected() -> None:
    client = TestClient(app)
    request = client.build_request("GET", "/openapi.json")
    del request.headers["host"]

    response = client.send(request)

    assert response.status_code == 400


def test_host_validation_runs_before_cors_and_preserves_origin_checks() -> None:
    client = TestClient(app, base_url="http://localhost")
    headers = {
        "Origin": get_settings().frontend_origin,
        "Access-Control-Request-Method": "POST",
    }

    allowed = client.options("/api/auth/login", headers=headers)
    rejected = client.options("/api/auth/login", headers={**headers, "Host": "untrusted.example"})
    foreign_write = client.post("/api/auth/logout", headers={"Origin": "https://untrusted.example"})

    assert allowed.status_code == 200
    assert rejected.status_code == 400
    assert foreign_write.status_code == 403
