"""
Passwords and tokens.

Three defects in the previous version made login both broken and unsafe, and
all three are worth naming because the shapes recur:

  1. The bcrypt hash was wrapped in str() before being stored. bcrypt returns
     bytes, so str() produced the literal text  b'$2b$12$...'  including the
     letter b and the quotes. Nothing can ever verify against that.

  2. The lookup did user_query[0] on the result of .first(), which is a model
     object and not a sequence, so every login attempt raised TypeError.

  3. The password check was called and its answer thrown away:

         __check_pwd(userdata.password, user.password)
         return True

     Once the TypeError above was fixed, that line would have let ANY password
     through for any email that existed.

Tokens are JSON Web Tokens. The token says who you are and what role you hold,
it is signed, and it expires. Nothing else about a session is stored on the
server, which is what lets the API stay stateless.
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

logger = logging.getLogger("crovia.auth")

ALGORITHM = "HS256"
TOKEN_TTL_HOURS = float(os.getenv("JWT_TTL_HOURS", "12"))


def _secret() -> str:
    """
    The signing key.

    If none is configured we generate a random one at startup rather than
    falling back to a fixed default. A known default key means anyone who has
    read the source can mint an admin token, which is worse than the
    inconvenience of every session ending when the server restarts.
    """
    key = os.getenv("JWT_SECRET", "").strip()
    if key:
        return key
    if not hasattr(_secret, "_generated"):
        _secret._generated = secrets.token_urlsafe(48)
        logger.warning("JWT_SECRET is not set - using a random key for this run. "
                       "Everyone is signed out when the server restarts. "
                       "Set JWT_SECRET before deploying.")
    return _secret._generated


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------

def hash_password(plain: str, rounds: int = 12) -> str:
    """Hash a password for storage. Returns text, ready for a String column."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=rounds)).decode()


def verify_password(plain: str, stored: str | bytes | None) -> bool:
    """
    Check a password against a stored hash. Never raises.

    Accounts created before the storage bug was fixed hold the text
    b'$2b$12$...' rather than the hash itself. Those are unwrapped here so
    existing accounts keep working instead of being silently locked out.
    """
    if not stored:
        return False
    if isinstance(stored, bytes):
        stored = stored.decode(errors="ignore")
    if stored.startswith("b'") and stored.endswith("'"):
        stored = stored[2:-1]
    try:
        return bcrypt.checkpw(plain.encode(), stored.encode())
    except (ValueError, TypeError):
        # A malformed hash is a failed login, not a server error.
        return False


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

def create_access_token(*, user_id: str, role: str, username: str,
                        email: str) -> tuple[str, int]:
    """
    Mint a signed token. Returns the token and how many seconds it lasts.

    The role travels inside the token so a protected route can decide what the
    caller may do without another database read on every request. It is safe to
    trust because the token is signed - changing the role would break the
    signature.
    """
    ttl = timedelta(hours=TOKEN_TTL_HOURS)
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "username": username,
        "email": email,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM), int(ttl.total_seconds())


def decode_token(token: str) -> dict | None:
    """Read a token back. Returns None if it is invalid, tampered with, or expired."""
    try:
        return jwt.decode(token, _secret(), algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        logger.info("token rejected: expired")
    except jwt.InvalidTokenError as exc:
        logger.info("token rejected: %s", exc)
    return None
