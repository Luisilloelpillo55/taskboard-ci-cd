import hashlib
import logging
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
logger = logging.getLogger(__name__)


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: SecretStr = Field(min_length=12, max_length=128)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: SecretStr = Field(max_length=128)


class UpdateAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: SecretStr = Field(max_length=128)
    email: EmailStr | None = None
    new_password: Annotated[
        SecretStr, Field(min_length=12, max_length=128)
    ] | None = None


class DeleteAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: SecretStr = Field(max_length=128)


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


def _require_current_password(user_id: int, current_password: SecretStr) -> None:
    with connect() as connection:
        user = connection.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user_id,)
        ).fetchone()

    if user is None:
        raise _invalid_credentials()
    if not password_hash.verify(
        current_password.get_secret_value(), user["password_hash"]
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La contraseña actual es incorrecta.",
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
    logger.info("User registered")
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
        logger.warning(
            "Login rejected",
            extra={
                "event_type": "api_request_error",
                "component": "backend",
                "http_method": "POST",
                "http_route": "/api/auth/login",
                "http_status_code": status.HTTP_401_UNAUTHORIZED,
                "error_type": "AuthenticationError",
                "failure_reason": "Invalid credentials.",
            },
        )
        raise _invalid_credentials()

    with connect() as connection:
        token = _new_session(connection, user["id"])
    _set_session_cookie(response, token)
    logger.info("User logged in")
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
        logger.info("User logged out")
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
    if user is None:
        raise _invalid_credentials()
    return UserPublic.model_validate(dict(user))


CurrentUser = Annotated[UserPublic, Depends(get_current_user)]


@router.get("/me", response_model=UserPublic)
def current_user(user: CurrentUser) -> dict:
    return user


@router.patch("/me", response_model=UserPublic)
def update_current_user(
    payload: UpdateAccountRequest,
    request: Request,
    user: CurrentUser,
) -> dict:
    fields = payload.model_fields_set
    if not fields.intersection({"email", "new_password"}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Indica un correo o una nueva contraseña para actualizar.",
        )
    if "email" in fields and payload.email is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El correo no puede ser nulo.",
        )
    if "new_password" in fields and payload.new_password is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La nueva contraseña no puede ser nula.",
        )

    _require_current_password(user.id, payload.current_password)
    changes: list[str] = []
    values: list[str] = []
    if payload.email is not None:
        changes.append("email = ?")
        values.append(_normalized_email(payload.email))
    if payload.new_password is not None:
        changes.append("password_hash = ?")
        values.append(password_hash.hash(payload.new_password.get_secret_value()))

    try:
        with connect() as connection:
            cursor = connection.execute(
                f"UPDATE users SET {', '.join(changes)} WHERE id = ?",
                (*values, user.id),
            )
            if cursor.rowcount == 0:
                raise _invalid_credentials()
            if payload.new_password is not None:
                token = request.cookies.get(SESSION_COOKIE)
                if token is None:
                    raise _invalid_credentials()
                connection.execute(
                    "DELETE FROM sessions WHERE user_id = ? AND token_hash != ?",
                    (user.id, _token_digest(token)),
                )
            updated_user = connection.execute(
                "SELECT id, email, created_at FROM users WHERE id = ?",
                (user.id,),
            ).fetchone()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con ese correo.",
        ) from exc

    logger.info("User account updated")
    return dict(updated_user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_current_user(
    payload: DeleteAccountRequest,
    response: Response,
    user: CurrentUser,
) -> Response:
    _require_current_password(user.id, payload.current_password)

    with connect() as connection:
        connection.execute("DELETE FROM tasks WHERE user_id = ?", (user.id,))
        cursor = connection.execute("DELETE FROM users WHERE id = ?", (user.id,))
        if cursor.rowcount == 0:
            raise _invalid_credentials()

    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        secure=_cookie_is_secure(),
        httponly=True,
        samesite="lax",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    logger.info("User account deleted")
    return response
