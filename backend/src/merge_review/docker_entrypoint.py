import fcntl
import os
import secrets
import sys
from pathlib import Path

from merge_review.config import DEFAULT_AUTH_SECRET

AUTH_SECRET_FILE = Path("/app/secrets/auth_secret")


def load_or_create_auth_secret(path: Path) -> str:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "r+", encoding="utf-8") as secret_file:
        # Serialize first startup across containers sharing the volume
        fcntl.flock(secret_file, fcntl.LOCK_EX)
        os.fchmod(secret_file.fileno(), 0o600)
        secret = secret_file.read().strip()
        if not secret:
            secret = secrets.token_urlsafe(32)
            secret_file.seek(0)
            secret_file.write(secret + "\n")
            secret_file.truncate()
            secret_file.flush()
            os.fsync(secret_file.fileno())
        if len(secret) < 32 or secret == DEFAULT_AUTH_SECRET:
            raise RuntimeError("Stored auth secret is invalid")
        return secret


def main() -> None:
    command = sys.argv[1:]
    if not command:
        raise SystemExit("Expected a container command")
    secret = os.environ.get("MERGE_REVIEW_AUTH_SECRET")
    if not secret or secret == DEFAULT_AUTH_SECRET:
        os.environ["MERGE_REVIEW_AUTH_SECRET"] = load_or_create_auth_secret(AUTH_SECRET_FILE)
    elif len(secret) < 32:
        raise RuntimeError("MERGE_REVIEW_AUTH_SECRET must contain at least 32 characters")
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
