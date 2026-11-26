import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr
from pwdlib import PasswordHash

from app.database import connect


SESSION_COOKIE = "taskboard_session"
SESSION_DURATION = timedelta(days=7)
SESSION_MAX_AGE = int(SESSION_DURATION.total_seconds())

router = APIRouter(prefix="/api/auth", tags=["authentication"])
password_hash = PasswordHash.recommended()
_dummy_password_hash = password_hash.hash(secrets.token_urlsafe(32))


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: SecretStr = Field(min_length=12, max_length=128)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: SecretStr = Field(max_length=128)


class UserPublic(BaseModel):
    id: int
    email: EmailStr
    created_at: str


def _normalized_email(email: EmailStr) -> str:
    return str(email).strip().casefold()


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_session(connection: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + SESSION_DURATION).isoformat()
    connection.execute(
        "INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
        (user_id, _token_digest(token), expires_at),
    )
    return token


def _cookie_is_secure() -> bool:
    value = os.getenv("COOKIE_SECURE", "false").strip().lower()
    if value not in {"true", "false"}:
        raise RuntimeError("COOKIE_SECURE must be set to 'true' or 'false'.")
    return value == "true"


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_MAX_AGE,
        path="/",
        secure=_cookie_is_secure(),
        httponly=True,
        samesite="lax",
    )


def _invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Correo o contraseña incorrectos.",
    )


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, response: Response) -> dict:
    email = _normalized_email(payload.email)
    hashed_password = password_hash.hash(payload.password.get_secret_value())

    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?) "
            "ON CONFLICT(email) DO NOTHING",
            (email, hashed_password),
        )
        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya existe una cuenta con ese correo.",
            )
        user = connection.execute(
            "SELECT id, email, created_at FROM users WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        token = _new_session(connection, user["id"])

    _set_session_cookie(response, token)
    return dict(user)


@router.post("/login", response_model=UserPublic)
def login(payload: LoginRequest, response: Response) -> dict:
    email = _normalized_email(payload.email)
    with connect() as connection:
        user = connection.execute(
            "SELECT id, email, password_hash, created_at FROM users WHERE email = ?",
            (email,),
        ).fetchone()

    stored_hash = user["password_hash"] if user else _dummy_password_hash
    password_matches = password_hash.verify(
        payload.password.get_secret_value(), stored_hash
    )
    if user is None or not password_matches:
        raise _invalid_credentials()

    with connect() as connection:
        token = _new_session(connection, user["id"])
    _set_session_cookie(response, token)
    return {
        "id": user["id"],
        "email": user["email"],
        "created_at": user["created_at"],
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response) -> Response:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        with connect() as connection:
            connection.execute(
                "DELETE FROM sessions WHERE token_hash = ?", (_token_digest(token),)
            )
    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        secure=_cookie_is_secure(),
        httponly=True,
        samesite="lax",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


def get_current_user(request: Request) -> UserPublic:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise _invalid_credentials()

    now = datetime.now(timezone.utc).isoformat()
    token_hash = _token_digest(token)
    with connect() as connection:
        user = connection.execute(
            """
            SELECT users.id, users.email, users.created_at
            FROM users
            JOIN sessions ON sessions.user_id = users.id
            WHERE sessions.token_hash = ? AND sessions.expires_at > ?
            """,
            (token_hash, now),
        ).fetchone()
        if user is None:
            connection.execute(
                "DELETE FROM sessions WHERE token_hash = ? AND expires_at <= ?",
                (token_hash, now),
            )
            raise _invalid_credentials()
    return UserPublic.model_validate(dict(user))


CurrentUser = Annotated[UserPublic, Depends(get_current_user)]


@router.get("/me", response_model=UserPublic)
def current_user(user: CurrentUser) -> dict:
    return user
