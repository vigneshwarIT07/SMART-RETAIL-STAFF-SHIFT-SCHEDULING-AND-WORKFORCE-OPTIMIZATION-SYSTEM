"""Password hashing and JSON Web Token helpers.

The ``bcrypt`` library is used directly instead of ``passlib``. ``passlib``
1.7.4 (the last release) is incompatible with ``bcrypt`` 5.x: it reads the
library's internal state through a removed wrapper-detection path and raises
``ValueError: password cannot be longer than 72 bytes`` for every password.
Calling ``bcrypt`` directly removes that failure mode entirely and keeps the
dependency tree smaller.

All functions here are pure and side-effect free with respect to the database,
which makes them straightforward to unit test.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt

from app.core.config import settings

#: bcrypt silently ignores bytes past 72, so we truncate explicitly instead of
#: relying on implementation behaviour.
MAX_PASSWORD_BYTES = 72


def _encode_password(password: str) -> bytes:
    """Return the UTF-8 bytes of ``password`` truncated to bcrypt's limit.

    Args:
        password: The plaintext password supplied by the user.

    Returns:
        The (possibly truncated) UTF-8 encoded password.
    """
    return password.encode("utf-8")[:MAX_PASSWORD_BYTES]


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt.

    Args:
        password: The plaintext password.

    Returns:
        The bcrypt hash, as an ASCII string safe for database storage.
    """
    return bcrypt.hashpw(_encode_password(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a plaintext password against a stored bcrypt hash.

    Args:
        plain_password: The password supplied at login time.
        hashed_password: The hash previously produced by :func:`hash_password`.

    Returns:
        True when the password matches, False otherwise (including when the
        stored hash is malformed).
    """
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(
            _encode_password(plain_password), hashed_password.encode("utf-8")
        )
    except (ValueError, TypeError):
        # A malformed stored hash must never authenticate anybody.
        return False


def create_access_token(
    subject: str,
    role: str,
    store_id: str,
    expires_minutes: Optional[int] = None,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """Create a signed JWT for an authenticated user.

    The token carries only server-derived identity claims: the user id, the role
    read from the database, and the store the user belongs to. Nothing that the
    browser can influence is encoded here.

    Args:
        subject: The user's primary key.
        role: The user's role value (``manager`` or ``employee``).
        store_id: The store the user is scoped to.
        expires_minutes: Override for the configured expiry window.
        extra_claims: Additional claims merged into the token payload.

    Returns:
        An encoded JWT string.
    """
    now = datetime.now(timezone.utc)
    lifetime = (
        expires_minutes
        if expires_minutes is not None
        else settings.access_token_expire_minutes
    )
    payload: Dict[str, Any] = {
        "sub": subject,
        "role": role,
        "store_id": store_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=lifetime)).timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and verify a JWT.

    Args:
        token: The encoded token supplied by the client.

    Returns:
        The decoded payload.

    Raises:
        jwt.PyJWTError: if the token is expired, tampered with, or malformed.
    """
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "sub"]},
    )