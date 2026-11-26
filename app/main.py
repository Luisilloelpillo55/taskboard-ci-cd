from contextlib import asynccontextmanager
from collections.abc import Awaitable, Callable
from enum import Enum
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.responses import FileResponse, Response as StarletteResponse

from app.auth import CurrentUser, router as auth_router
from app.database import connect, initialize_database


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
    yield


app = FastAPI(title="Taskboard", version="1.0.0", lifespan=lifespan)
app.include_router(auth_router)
static_directory = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_directory), name="static")


@app.middleware("http")
async def disable_api_caching(
    request: Request,
    call_next: Callable[[Request], Awaitable[StarletteResponse]],
) -> StarletteResponse:
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


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
    return Response(status_code=status.HTTP_204_NO_CONTENT)
