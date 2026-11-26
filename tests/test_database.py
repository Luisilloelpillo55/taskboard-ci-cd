import sqlite3
from contextlib import closing

import pytest

from app.database import connect, initialize_database


def test_database_initialization_is_idempotent_and_preserves_tasks(client):
    assert client.post(
        "/api/auth/register",
        json={"email": "database@example.com", "password": "GoodPassphrase2026!"},
    ).status_code == 201
    created = client.post("/api/tasks", json={"title": "Keep me"}).json()

    initialize_database()

    assert client.get("/api/tasks").json() == [created]


def test_unsupported_task_schema_fails_explicitly(tmp_path, monkeypatch):
    database_path = tmp_path / "unsupported.db"
    monkeypatch.setenv("TASKS_DB_PATH", str(database_path))
    with closing(sqlite3.connect(database_path)) as connection:
        with connection:
            connection.execute(
                "CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT)"
            )

    with pytest.raises(RuntimeError, match="unsupported schema"):
        initialize_database()

    with connect() as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'tasks'"
        ).fetchone() is not None


@pytest.mark.parametrize(
    ("title", "task_status"),
    [
        pytest.param("", "todo", id="empty-title"),
        pytest.param("   ", "todo", id="whitespace-title"),
        pytest.param("t" * 121, "todo", id="title-too-long"),
        pytest.param("Valid title", "blocked", id="unknown-status"),
    ],
)
def test_database_constraints_reject_invalid_task_rows(client, title, task_status):
    with pytest.raises(sqlite3.IntegrityError):
        with connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks (title, description, status, created_at)
                VALUES (?, '', ?, '2026-01-01T00:00:00Z')
                """,
                (title, task_status),
            )


def test_home_page_serves_the_taskboard_interface(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<title>Taskboard | Organiza tu trabajo</title>" in response.text


@pytest.mark.parametrize(
    ("path", "content_type", "expected_content"),
    [
        pytest.param(
            "/static/app.js",
            "javascript",
            "async function initialize()",
            id="application-script",
        ),
        pytest.param(
            "/static/styles.css",
            "text/css",
            "@media (max-width: 560px)",
            id="responsive-styles",
        ),
    ],
)
def test_frontend_assets_are_served(client, path, content_type, expected_content):
    response = client.get(path)

    assert response.status_code == 200
    assert content_type in response.headers["content-type"]
    assert expected_content in response.text
