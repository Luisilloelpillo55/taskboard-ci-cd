import logging
import re
from time import perf_counter
from contextlib import asynccontextmanager
from collections.abc import Awaitable, Callable
from enum import Enum
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import FileResponse, Response as StarletteResponse

from app.auth import CurrentUser, router as auth_router
from app.database import connect, initialize_database
from app.telemetry import configure_telemetry, shutdown_telemetry


logger = logging.getLogger(__name__)
_SENSITIVE_VALUE = re.compile(
    r"((?:authorization|password|passwd|token|secret|api[_-]?key|cookie)\s*[:=]\s*)"
    r'(?:"[^"]*"|\'[^\']*\'|(?:Basic|Bearer)\s+[A-Za-z0-9._~+/-]+=*|[^\s,;]+)',
    re.IGNORECASE,
)
_AUTH_HEADER = re.compile(
    r"\b(Basic|Bearer)\s+[A-Za-z0-9._~+/-]+=*",
    re.IGNORECASE,
)


def _sanitize_reason(reason: str) -> str:
    sanitized = _SENSITIVE_VALUE.sub(r"\1[REDACTED]", reason)
    return _AUTH_HEADER.sub(r"\1 [REDACTED]", sanitized)[:1000]


def _request_failure_fields(
    request: Request,
    *,
    status_code: int,
    error_type: str,
    failure_reason: str,
) -> dict[str, Any]:
    started_at = getattr(request.state, "started_at", None)
    duration_ms = (
        round((perf_counter() - started_at) * 1000, 3)
        if started_at is not None
        else None
    )
    return {
        "event_type": "api_request_error",
        "component": "backend",
        "http_method": request.method,
        "http_route": request.url.path,
        "http_status_code": status_code,
        "error_type": error_type,
        "failure_reason": _sanitize_reason(failure_reason),
        "duration_ms": duration_ms,
    }


def _log_request_failure(
    request: Request,
    *,
    status_code: int,
    error_type: str,
    failure_reason: str,
) -> None:
    level = logging.ERROR if status_code >= 500 else logging.WARNING
    logger.log(
        level,
        "API request failed: %s %s returned HTTP %s",
        request.method,
        request.url.path,
        status_code,
        extra=_request_failure_fields(
            request,
            status_code=status_code,
            error_type=error_type,
            failure_reason=failure_reason,
        ),
    )


class TaskStatus(str, Enum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"


class TaskCreate(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=120)]
    description: Annotated[str, Field(max_length=500)] = ""

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    description: Annotated[str, Field(max_length=500)] | None = None
    status: TaskStatus | None = None

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class Task(TaskCreate):
    id: int
    status: TaskStatus
    created_at: str


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    try:
        yield
    finally:
        shutdown_telemetry()


app = FastAPI(title="Taskboard", version="1.0.0", lifespan=lifespan)
configure_telemetry(app)
app.include_router(auth_router)
static_directory = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_directory), name="static")


@app.middleware("http")
async def disable_api_caching(
    request: Request,
    call_next: Callable[[Request], Awaitable[StarletteResponse]],
) -> StarletteResponse:
    if request.url.path.startswith("/api/"):
        request.state.started_at = perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        if request.url.path.startswith("/api/"):
            _log_request_failure(
                request,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                error_type=type(exc).__name__,
                failure_reason=str(exc) or "Unhandled API exception.",
            )
        raise
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(StarletteHTTPException)
async def log_http_exception(
    request: Request,
    exc: StarletteHTTPException,
) -> StarletteResponse:
    if not (
        request.url.path == "/api/auth/login"
        and exc.status_code == status.HTTP_401_UNAUTHORIZED
    ):
        reason = exc.detail if isinstance(exc.detail, str) else type(exc.detail).__name__
        _log_request_failure(
            request,
            status_code=exc.status_code,
            error_type=type(exc).__name__,
            failure_reason=reason,
        )
    return await http_exception_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def log_request_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> StarletteResponse:
    reasons = []
    for error in exc.errors()[:10]:
        location = ".".join(str(part) for part in error.get("loc", ()))
        reasons.append(f"{location}: {error.get('msg', 'Invalid input')}")
    _log_request_failure(
        request,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        error_type="RequestValidationError",
        failure_reason="; ".join(reasons) or "Request validation failed.",
    )
    return await request_validation_exception_handler(request, exc)


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(static_directory / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/tasks", response_model=list[Task])
def list_tasks(user: CurrentUser) -> list[dict]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT id, title, description, status, created_at "
            "FROM tasks WHERE user_id = ? ORDER BY id DESC",
            (user.id,),
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/tasks", response_model=Task, status_code=status.HTTP_201_CREATED)
def create_task(task: TaskCreate, user: CurrentUser) -> dict:
    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO tasks (title, description, status, created_at, user_id) "
            "VALUES (?, ?, 'todo', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), ?)",
            (task.title.strip(), task.description.strip(), user.id),
        )
        row = connection.execute(
            "SELECT id, title, description, status, created_at "
            "FROM tasks WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    logger.info(
        "Task created",
        extra={
            "event_name": "task.created",
            "component": "backend",
            "task_id": row["id"],
        },
    )
    return dict(row)


@app.patch("/api/tasks/{task_id}", response_model=Task)
def update_task(task_id: int, update: TaskUpdate, user: CurrentUser) -> dict:
    changes = update.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="Provide at least one field to update.")
    if any(value is None for value in changes.values()):
        raise HTTPException(status_code=422, detail="Task fields cannot be null.")
    if "description" in changes and changes["description"] is not None:
        changes["description"] = changes["description"].strip()
    if "status" in changes and changes["status"] is not None:
        changes["status"] = changes["status"].value

    assignments = ", ".join(f"{field} = ?" for field in changes)
    with connect() as connection:
        cursor = connection.execute(
            f"UPDATE tasks SET {assignments} WHERE id = ? AND user_id = ?",
            (*changes.values(), task_id, user.id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Task not found.")
        row = connection.execute(
            "SELECT id, title, description, status, created_at "
            "FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
    logger.info(
        "Task updated",
        extra={
            "event_name": "task.updated",
            "component": "backend",
            "task_id": task_id,
        },
    )
    return dict(row)


@app.delete("/api/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, user: CurrentUser) -> Response:
    with connect() as connection:
        cursor = connection.execute(
            "DELETE FROM tasks WHERE id = ? AND user_id = ?",
            (task_id, user.id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Task not found.")
    logger.info(
        "Task deleted",
        extra={
            "event_name": "task.deleted",
            "component": "backend",
            "task_id": task_id,
        },
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
