import os
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import pytest
from merge_review import docker_entrypoint
from merge_review.config import DEFAULT_AUTH_SECRET


def test_generated_secret_is_private_and_reused(tmp_path: Path) -> None:
    path = tmp_path / "secrets" / "auth_secret"

    first = docker_entrypoint.load_or_create_auth_secret(path)
    second = docker_entrypoint.load_or_create_auth_secret(path)

    assert first == second
    assert len(first) >= 32
    assert first != DEFAULT_AUTH_SECRET
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.read_text().strip() == first


def test_concurrent_starts_share_one_secret(tmp_path: Path) -> None:
    path = tmp_path / "auth_secret"

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(docker_entrypoint.load_or_create_auth_secret, [path] * 4))

    assert len(set(results)) == 1
    assert path.read_text().strip() == results[0]


@pytest.mark.parametrize("secret", ["too-short", DEFAULT_AUTH_SECRET])
def test_invalid_stored_secret_stops_startup(tmp_path: Path, secret: str) -> None:
    path = tmp_path / "auth_secret"
    path.write_text(secret)

    with pytest.raises(RuntimeError, match="Stored auth secret is invalid"):
        docker_entrypoint.load_or_create_auth_secret(path)

    assert path.read_text() == secret


@pytest.mark.parametrize("configured", [None, "", DEFAULT_AUTH_SECRET])
def test_entrypoint_supplies_the_persisted_secret(tmp_path: Path, monkeypatch, configured) -> None:
    path = tmp_path / "auth_secret"
    monkeypatch.setattr(docker_entrypoint, "AUTH_SECRET_FILE", path)
    monkeypatch.setattr(docker_entrypoint.sys, "argv", ["entrypoint", "python", "-m", "example"])
    monkeypatch.setenv("MERGE_REVIEW_AUTH_SECRET", configured or "")
    if configured is None:
        monkeypatch.delenv("MERGE_REVIEW_AUTH_SECRET")
    execute = Mock()
    monkeypatch.setattr(docker_entrypoint.os, "execvp", execute)

    docker_entrypoint.main()

    assert os.environ["MERGE_REVIEW_AUTH_SECRET"] == path.read_text().strip()
    execute.assert_called_once_with("python", ["python", "-m", "example"])


def test_explicit_secret_takes_precedence(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "auth_secret"
    secret = "explicit-private-secret-of-sufficient-length"
    monkeypatch.setattr(docker_entrypoint, "AUTH_SECRET_FILE", path)
    monkeypatch.setattr(docker_entrypoint.sys, "argv", ["entrypoint", "uvicorn", "example:app"])
    monkeypatch.setenv("MERGE_REVIEW_AUTH_SECRET", secret)
    execute = Mock()
    monkeypatch.setattr(docker_entrypoint.os, "execvp", execute)

    docker_entrypoint.main()

    assert os.environ["MERGE_REVIEW_AUTH_SECRET"] == secret
    assert not path.exists()
    execute.assert_called_once_with("uvicorn", ["uvicorn", "example:app"])


def test_short_explicit_secret_stops_startup(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(docker_entrypoint, "AUTH_SECRET_FILE", tmp_path / "auth_secret")
    monkeypatch.setattr(docker_entrypoint.sys, "argv", ["entrypoint", "uvicorn", "example:app"])
    monkeypatch.setenv("MERGE_REVIEW_AUTH_SECRET", "too-short")
    execute = Mock()
    monkeypatch.setattr(docker_entrypoint.os, "execvp", execute)

    with pytest.raises(RuntimeError, match="at least 32 characters"):
        docker_entrypoint.main()

    execute.assert_not_called()
