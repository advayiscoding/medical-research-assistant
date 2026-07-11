"""Authentication endpoints: register, login, and 'who am I'.

Thin adapter over services/auth.py: it translates domain errors into HTTP
status codes and issues the JWT. The /me route demonstrates the protected-route
pattern — declaring CurrentUserDep is the entire auth check.
"""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUserDep, DbDep, SettingsDep
from app.core.security import create_access_token
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserRead
from app.services.auth import (
    EmailAlreadyRegistered,
    InvalidCredentials,
    authenticate_user,
    register_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: DbDep, settings: SettingsDep) -> TokenResponse:
    try:
        user = await register_user(db, payload.email, payload.password, payload.full_name)
    except EmailAlreadyRegistered as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from exc
    await db.commit()
    # Log the user in immediately on register — one fewer round trip for the UI.
    return TokenResponse(access_token=create_access_token(str(user.id), settings))


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: DbDep, settings: SettingsDep) -> TokenResponse:
    try:
        user = await authenticate_user(db, payload.email, payload.password)
    except InvalidCredentials as exc:
        # Same message for bad email and bad password — never reveal which,
        # so an attacker can't enumerate valid accounts.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password") from exc
    return TokenResponse(access_token=create_access_token(str(user.id), settings))


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUserDep) -> UserRead:
    return UserRead(id=str(user.id), email=user.email, full_name=user.full_name)
