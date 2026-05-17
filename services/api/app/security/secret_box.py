"""Symmetric encryption for at-rest provider credentials.

Why: API keys persisted to the database must not be readable as plaintext from a
DB dump. Fernet provides authenticated AES-128-CBC + HMAC-SHA256 with a key
managed outside the database. The key is read once from settings; rotation is a
follow-up concern (Fernet supports MultiFernet for transparent rotation).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import threading

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class SecretBoxConfigError(RuntimeError):
    """Raised when the secret box cannot be constructed from current settings."""


class SecretBox:
    def __init__(self, key: bytes) -> None:
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        token = self._fernet.encrypt(plaintext.encode())
        return token.decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise SecretBoxConfigError(
                "stored secret could not be decrypted with the configured key"
            ) from exc


_lock = threading.Lock()
_singleton: SecretBox | None = None


def _derive_fernet_key(raw: str, environment: str) -> bytes:
    if raw:
        sanitized = raw.strip()
        if _is_valid_fernet_key(sanitized):
            return sanitized.encode("ascii")
        digest = hashlib.sha256(sanitized.encode()).digest()
        return base64.urlsafe_b64encode(digest)
    if environment == "production":
        raise SecretBoxConfigError(
            "SECRET_BOX_KEY must be set in production to encrypt provider credentials"
        )
    digest = hashlib.sha256(f"alphora-dev::{environment}".encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _is_valid_fernet_key(candidate: str) -> bool:
    try:
        decoded = base64.urlsafe_b64decode(candidate.encode("ascii"))
    except (ValueError, binascii.Error):
        return False
    return len(decoded) == 32


def get_secret_box() -> SecretBox:
    global _singleton
    with _lock:
        if _singleton is not None:
            return _singleton
        settings = get_settings()
        key = _derive_fernet_key(settings.secret_box_key, settings.environment)
        _singleton = SecretBox(key)
        return _singleton


def reset_secret_box_for_tests() -> None:
    global _singleton
    with _lock:
        _singleton = None


__all__ = [
    "SecretBox",
    "SecretBoxConfigError",
    "get_secret_box",
    "reset_secret_box_for_tests",
]
