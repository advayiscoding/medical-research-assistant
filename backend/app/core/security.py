"""Password hashing and JWT issuance/verification.

Uses bcrypt and PyJWT directly rather than passlib. passlib is effectively
unmaintained and its bcrypt backend breaks against bcrypt >= 4.x (the infamous
"module 'bcrypt' has no attribute '__about__'" error) — calling the libraries
directly is fewer moving parts and no compatibility shim to rot.

Two responsibilities, kept together because they're the whole auth primitive:
  - hash/verify passwords (bcrypt, which salts internally)
  - encode/decode short-lived JWT access tokens (HS256)
"""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import Settings


def hash_password(plain: str) -> str:
    # bcrypt has a 72-byte input limit and silently truncates beyond it; encode
    # and let bcrypt salt+hash. Store the full hash string (algorithm-tagged).
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        # Malformed hash in the DB — treat as non-match rather than 500.
        return False


def create_access_token(subject: str, settings: Settings) -> str:
    """Issue a signed token whose subject is the user id. Short-lived by design:
    no refresh-token rotation here (documented as future work), so we keep the
    access-token lifetime modest and re-login on expiry."""
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> str | None:
    """Return the subject (user id) if the token is valid and unexpired, else
    None. PyJWT verifies signature and expiry; any failure means 'not authed'."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    sub = payload.get("sub")
    return sub if isinstance(sub, str) else None
