from starlette.testclient import TestClient

from app.database import connect
from app.main import app


PASSWORD = "GoodPassphrase2026!"


def register(client, email, password=PASSWORD):
    return client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )


def test_account_update_changes_credentials_and_revokes_other_sessions(client):
    assert register(client, "original@example.com").status_code == 201
    with TestClient(app) as other_session:
        login = other_session.post(
            "/api/auth/login",
            json={"email": "original@example.com", "password": PASSWORD},
        )
        assert login.status_code == 200

        updated = client.patch(
            "/api/auth/me",
            json={
                "current_password": PASSWORD,
                "email": "Updated@Example.com",
                "new_password": "NewGoodPassphrase2026!",
            },
        )

        assert updated.status_code == 200
        assert updated.json()["email"] == "updated@example.com"
        assert client.get("/api/auth/me").json()["email"] == "updated@example.com"
        assert other_session.get("/api/auth/me").status_code == 401
        assert client.post(
            "/api/auth/login",
            json={"email": "original@example.com", "password": PASSWORD},
        ).status_code == 401
        assert client.post(
            "/api/auth/login",
            json={
                "email": "updated@example.com",
                "password": "NewGoodPassphrase2026!",
            },
        ).status_code == 200


def test_account_update_validates_fields_and_rejects_duplicate_email(client):
    assert register(client, "first@example.com").status_code == 201
    with TestClient(app) as other_user:
        assert register(other_user, "second@example.com").status_code == 201

        assert client.patch(
            "/api/auth/me", json={"current_password": PASSWORD}
        ).status_code == 400
        assert client.patch(
            "/api/auth/me",
            json={"current_password": PASSWORD, "email": None},
        ).status_code == 422
        assert client.patch(
            "/api/auth/me",
            json={"current_password": PASSWORD, "new_password": None},
        ).status_code == 422
        assert client.patch(
            "/api/auth/me",
            json={"current_password": PASSWORD, "new_password": "short"},
        ).status_code == 422
        assert client.patch(
            "/api/auth/me",
            json={"current_password": PASSWORD, "is_admin": True},
        ).status_code == 422
        assert client.patch(
            "/api/auth/me",
            json={
                "current_password": PASSWORD,
                "email": "SECOND@example.com",
            },
        ).status_code == 409
        assert client.patch(
            "/api/auth/me",
            json={
                "current_password": "WrongPassphrase2026!",
                "email": "changed@example.com",
            },
        ).status_code == 403
        assert client.get("/api/auth/me").json()["email"] == "first@example.com"


def test_account_deletion_requires_password_and_removes_only_own_data(client):
    assert register(client, "delete-me@example.com").status_code == 201
    own_task = client.post("/api/tasks", json={"title": "Remove with account"})
    assert own_task.status_code == 201

    with TestClient(app) as other_user:
        assert register(other_user, "keep-me@example.com").status_code == 201
        other_task = other_user.post(
            "/api/tasks", json={"title": "Keep other account task"}
        )
        assert other_task.status_code == 201

        rejected = client.request(
            "DELETE",
            "/api/auth/me",
            json={"current_password": "WrongPassphrase2026!"},
        )
        assert rejected.status_code == 403
        assert client.get("/api/auth/me").status_code == 200

        deleted = client.request(
            "DELETE",
            "/api/auth/me", json={"current_password": PASSWORD}
        )

        assert deleted.status_code == 204
        assert "Max-Age=0" in deleted.headers["set-cookie"]
        assert client.get("/api/auth/me").status_code == 401
        assert other_user.get("/api/auth/me").status_code == 200
        assert other_user.get("/api/tasks").json() == [other_task.json()]

    with connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM users WHERE email = 'delete-me@example.com'"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM tasks WHERE id = ?", (own_task.json()["id"],)
        ).fetchone()[0] == 0
