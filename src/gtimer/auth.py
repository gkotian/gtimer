from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets


DEFAULT_PASSWORD_FILE = Path("~/.config/gtimer/admin_password.json").expanduser()
_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 600_000


def password_file_exists(path: Path = DEFAULT_PASSWORD_FILE) -> bool:
    return path.exists()


def set_password(password: str, path: Path = DEFAULT_PASSWORD_FILE) -> None:
    if not password:
        raise ValueError("Password must not be empty")
    salt = secrets.token_bytes(16)
    digest = _derive(password, salt, _ITERATIONS)
    record = {
        "algorithm": _ALGORITHM,
        "iterations": _ITERATIONS,
        "salt": base64.b64encode(salt).decode("ascii"),
        "hash": base64.b64encode(digest).decode("ascii"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as password_file:
        json.dump(record, password_file, indent=2)
        password_file.write("\n")
    path.chmod(0o600)


def verify_password(password: str, path: Path = DEFAULT_PASSWORD_FILE) -> bool:
    with path.open("r", encoding="utf-8") as password_file:
        record = json.load(password_file)
    if record.get("algorithm") != _ALGORITHM:
        raise ValueError(f"Unsupported password algorithm: {record.get('algorithm')}")
    salt = base64.b64decode(record["salt"])
    expected = base64.b64decode(record["hash"])
    iterations = int(record["iterations"])
    actual = _derive(password, salt, iterations)
    return hmac.compare_digest(actual, expected)


def _derive(password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
