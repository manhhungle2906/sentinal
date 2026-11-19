"""Password hashing, token generation and digest helpers."""

from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a password with Argon2id."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against an Argon2 hash without leaking the reason."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False
    except Exception:
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except Exception:
        return True


def generate_token() -> str:
    """High-entropy opaque token (session id / CSRF token)."""
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    """One-way digest. Only the digest is persisted."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)


def generate_ingestion_key() -> tuple[str, str, str]:
    """Return (raw_key, prefix, digest) for a new ingestion credential.

    The raw key is shown to the operator exactly once.
    """
    prefix = "sn_" + secrets.token_hex(3)
    secret = secrets.token_urlsafe(32)
    raw = f"{prefix}.{secret}"
    return raw, prefix, token_digest(raw)


def key_prefix_of(raw_key: str) -> str:
    return raw_key.split(".", 1)[0][:12]
