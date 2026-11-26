import logging
import sqlite3

from starlette.testclient import TestClient

from app.main import app


def register_user(client, email="luis@example.com", password="ClaveSegura2026!"):
    return client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )


def test_health_endpoint(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_list_update_and_delete_task(client):
    assert client.get("/api/tasks").status_code == 401
    assert register_user(client).status_code == 201
    created = client.post(
        "/api/tasks",
        json={"title": "Planificar entrega", "description": "Revisar requisitos"},
    )
    assert created.status_code == 201
    task = created.json()
    assert task["title"] == "Planificar entrega"
    assert task["status"] == "todo"
    assert task["created_at"]

    listed = client.get("/api/tasks")
    assert listed.status_code == 200
    assert listed.json() == [task]

    updated = client.patch(f"/api/tasks/{task['id']}", json={"status": "done"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "done"

    deleted = client.delete(f"/api/tasks/{task['id']}")
    assert deleted.status_code == 204
    assert client.get("/api/tasks").json() == []


def test_task_validation_and_missing_task(client):
    assert register_user(client).status_code == 201
    assert client.post("/api/tasks", json={"title": "  "}).status_code == 422
    assert client.post("/api/tasks", json={"title": "x" * 121}).status_code == 422
    assert client.patch("/api/tasks/99", json={"status": "done"}).status_code == 404
    assert client.delete("/api/tasks/99").status_code == 404


def test_update_rejects_empty_or_null_fields(client):
    assert register_user(client).status_code == 201
    task = client.post("/api/tasks", json={"title": "Revisar datos"}).json()

    assert client.patch(f"/api/tasks/{task['id']}", json={}).status_code == 400
    assert client.patch(
        f"/api/tasks/{task['id']}", json={"status": None}
    ).status_code == 422


def test_legacy_database_migration_preserves_tasks(tmp_path, monkeypatch):
    database_path = tmp_path / "legacy.db"
    monkeypatch.setenv("TASKS_DB_PATH", str(database_path))
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO tasks (id, title, completed, created_at) "
            "VALUES (7, 'Tarea anterior', 1, '2026-01-02T03:04:05Z')"
        )

    with TestClient(app) as legacy_client:
        assert register_user(legacy_client).status_code == 201
        response = legacy_client.get("/api/tasks")
        created = legacy_client.post("/api/tasks", json={"title": "Tarea nueva"})

    assert response.status_code == 200
    assert response.json() == []
    assert created.status_code == 201
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT id, title, status, user_id FROM tasks WHERE id = 7"
        ).fetchone() == (7, "Tarea anterior", "done", None)


def test_registration_login_logout_and_password_validation(client, caplog):
    caplog.set_level(logging.INFO)
    assert client.get("/api/auth/me").status_code == 401
    short_password = client.post(
        "/api/auth/register",
        json={"email": "new@example.com", "password": "short"},
    )
    assert short_password.status_code == 422

    created = register_user(client, "New.User@example.com")
    assert created.status_code == 201
    assert created.json()["email"] == "new.user@example.com"
    assert "httponly" in created.headers["set-cookie"].lower()
    assert "samesite=lax" in created.headers["set-cookie"].lower()
    assert client.get("/api/auth/me").status_code == 200

    duplicate = register_user(client, "new.user@example.com")
    assert duplicate.status_code == 409
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401

    wrong_password = client.post(
        "/api/auth/login",
        json={"email": "new.user@example.com", "password": "Incorrecta2026!"},
    )
    assert wrong_password.status_code == 401
    login = client.post(
        "/api/auth/login",
        json={"email": "NEW.USER@example.com", "password": "ClaveSegura2026!"},
    )
    assert login.status_code == 200
    assert client.get("/api/auth/me").json()["email"] == "new.user@example.com"
    assert "Incorrecta2026!" not in caplog.text
    assert "ClaveSegura2026!" not in caplog.text
    assert "new.user@example.com" not in caplog.text
    assert "Login rejected" in caplog.text


def test_users_cannot_read_or_change_each_others_tasks(tmp_path, monkeypatch):
    monkeypatch.setenv("TASKS_DB_PATH", str(tmp_path / "shared.db"))
    with TestClient(app) as first_user:
        assert register_user(first_user, "first@example.com").status_code == 201
        task = first_user.post(
            "/api/tasks", json={"title": "Tarea privada"}
        ).json()

        with TestClient(app) as second_user:
            assert register_user(second_user, "second@example.com").status_code == 201
            assert second_user.get("/api/tasks").json() == []
            assert second_user.patch(
                f"/api/tasks/{task['id']}", json={"status": "done"}
            ).status_code == 404
            assert second_user.delete(f"/api/tasks/{task['id']}").status_code == 404


def test_previous_authenticated_schema_migrates_tasks_as_unowned(
    tmp_path, monkeypatch
):
    database_path = tmp_path / "previous.db"
    monkeypatch.setenv("TASKS_DB_PATH", str(database_path))
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'todo',
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO tasks (title, status, created_at) "
            "VALUES ('Tarea existente', 'in_progress', '2026-01-02T03:04:05Z')"
        )

    with TestClient(app) as migrated_client:
        assert register_user(migrated_client).status_code == 201
        assert migrated_client.get("/api/tasks").json() == []
        created = migrated_client.post("/api/tasks", json={"title": "Tarea nueva"})

    assert created.status_code == 201
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            "SELECT title, status, user_id FROM tasks ORDER BY id"
        ).fetchall()
    assert rows == [
        ("Tarea existente", "in_progress", None),
        ("Tarea nueva", "todo", 1),
    ]