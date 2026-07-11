"""Authentication business logic: registration and credential verification.

Kept out of the route so the same operations are callable from tests or a CLI,
and so the route stays a thin HTTP adapter. Raises domain errors; the route
layer maps them to HTTP status codes.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models import User


class EmailAlreadyRegistered(Exception):
    """Raised when registering an email that already exists."""


class InvalidCredentials(Exception):
    """Raised when login email/password don't match."""


async def register_user(
    db: AsyncSession, email: str, password: str, full_name: str | None
) -> User:
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        raise EmailAlreadyRegistered(email)

    user = User(email=email, hashed_password=hash_password(password), full_name=full_name)
    db.add(user)
    await db.flush()
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    # Verify even when the user is missing? We short-circuit here for simplicity.
    # (A constant-time dummy verify would harden against user-enumeration timing
    # attacks; noted as a future hardening step.)
    if user is None or not verify_password(password, user.hashed_password):
        raise InvalidCredentials()
    return user
