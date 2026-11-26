import hashlib
from http.cookies import SimpleCookie

import pytest

from app.auth import SESSION_COOKIE, SESSION_MAX_AGE
from app.database import connect


PASSWORD = "GoodPassphrase2026!"


def register(client, email="tester@example.com", password=PASSWORD):
    return client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )


def authenticated_client(client):
    response = register(client)
    assert response.status_code == 201
    return client


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({}, id="empty-body"),
        pytest.param({"email": "tester@example.com"}, id="missing-password"),
        pytest.param({"password": PASSWORD}, id="missing-email"),
        pytest.param(
            {"email": "not-an-email", "password": PASSWORD}, id="invalid-email"
        ),
        pytest.param(
            {"email": None, "password": PASSWORD}, id="null-email"
        ),
        pytest.param(
            {"email": "tester@example.com", "password": None},
            id="null-password",
        ),
        pytest.param(
            {"email": "tester@example.com", "password": "p" * 11},
            id="password-below-minimum",
        ),
        pytest.param(
            {"email": "tester@example.com", "password": "p" * 129},
            id="password-above-maximum",
        ),
        pytest.param(
            {
                "email": "tester@example.com",
                "password": PASSWORD,
                "is_admin": True,
            },
            id="unexpected-field",
        ),
    ],
)
def test_registration_rejects_malformed_payloads(client, payload):
    assert client.post("/api/auth/register", json=payload).status_code == 422


@pytest.mark.parametrize("password_length", [12, 128], ids=["minimum", "maximum"])
def test_registration_accepts_password_length_boundaries(client, password_length):
    response = register(
        client,
        email=f"boundary-{password_length}@example.com",
        password="p" * password_length,
    )

    assert response.status_code == 201


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(
            {"email": "not-an-email", "password": PASSWORD}, id="invalid-email"
        ),
        pytest.param({"email": "tester@example.com"}, id="missing-password"),
        pytest.param(
            {"email": "tester@example.com", "password": None},
            id="null-password",
        ),
        pytest.param(
            {"email": "tester@example.com", "password": "p" * 129},
            id="password-above-maximum",
        ),
        pytest.param(
            {
                "email": "tester@example.com",
                "password": PASSWORD,
                "is_admin": True,
            },
            id="unexpected-field",
        ),
    ],
)
def test_login_rejects_malformed_payloads(client, payload):
    assert client.post("/api/auth/login", json=payload).status_code == 422


@pytest.mark.parametrize(
    "user_exists",
    [pytest.param(False, id="unknown-email"), pytest.param(True, id="wrong-password")],
)
def test_login_does_not_disclose_whether_an_account_exists(client, user_exists):
    email = "known@example.com" if user_exists else "unknown@example.com"
    if user_exists:
        assert register(client, email=email).status_code == 201

    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "WrongPassphrase2026!"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Correo o contraseña incorrectos."}


def test_auth_responses_never_expose_passwords_or_session_tokens(client):
    registration = register(client)
    login = client.post(
        "/api/auth/login",
        json={"email": "tester@example.com", "password": PASSWORD},
    )
    current_user = client.get("/api/auth/me")

    for response in (registration, login, current_user):
        assert response.status_code == 201 or response.status_code == 200
        assert set(response.json()) == {"id", "email", "created_at"}
        assert "password" not in response.text
        assert "token" not in response.text


@pytest.mark.parametrize(
    ("secure_setting", "secure_expected"),
    [("false", False), ("true", True)],
    ids=["http-cookie", "secure-cookie"],
)
def test_session_cookie_security_attributes(
    client, monkeypatch, secure_setting, secure_expected
):
    monkeypatch.setenv("COOKIE_SECURE", secure_setting)
    response = register(client)
    cookies = SimpleCookie()
    cookies.load(response.headers["set-cookie"])
    session_cookie = cookies[SESSION_COOKIE]

    assert response.status_code == 201
    assert session_cookie["httponly"]
    assert session_cookie["samesite"] == "lax"
    assert session_cookie["path"] == "/"
    assert session_cookie["max-age"] == str(SESSION_MAX_AGE)
    assert bool(session_cookie["secure"]) is secure_expected


def test_invalid_cookie_security_setting_fails_explicitly(client, monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "yes")

    with pytest.raises(RuntimeError, match="COOKIE_SECURE must be set"):
        register(client)


def test_expired_session_is_rejected_and_removed(client):
    assert register(client).status_code == 201
    token = client.cookies.get(SESSION_COOKIE)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with connect() as connection:
        connection.execute(
            "UPDATE sessions SET expires_at = ? WHERE token_hash = ?",
            ("2000-01-01T00:00:00+00:00", token_hash),
        )

    response = client.get("/api/auth/me")

    assert response.status_code == 401
    with connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM sessions WHERE token_hash = ?", (token_hash,)
        ).fetchone()[0] == 0


def test_session_token_is_stored_only_as_a_hash(client):
    assert register(client).status_code == 201
    token = client.cookies.get(SESSION_COOKIE)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    with connect() as connection:
        stored_hashes = [
            row["token_hash"]
            for row in connection.execute("SELECT token_hash FROM sessions")
        ]

    assert token_hash in stored_hashes
    assert token not in stored_hashes


def test_logout_without_a_session_is_idempotent(client):
    first = client.post("/api/auth/logout")
    second = client.post("/api/auth/logout")

    assert first.status_code == 204
    assert second.status_code == 204
    assert "Max-Age=0" in second.headers["set-cookie"]


@pytest.mark.parametrize(
    ("method", "path"),
    [
        pytest.param("GET", "/api/health", id="health"),
        pytest.param("GET", "/api/auth/me", id="current-user"),
        pytest.param("GET", "/api/tasks", id="task-list"),
        pytest.param("POST", "/api/auth/logout", id="logout"),
    ],
)
def test_api_responses_disable_caching(client, method, path):
    response = client.request(method, path)

    assert "no-store" in response.headers["cache-control"].lower()


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        pytest.param(
            "POST",
            "/api/tasks",
            {"title": "Unauthenticated"},
            id="create-task",
        ),
        pytest.param(
            "PATCH",
            "/api/tasks/1",
            {"status": "done"},
            id="update-task",
        ),
        pytest.param("DELETE", "/api/tasks/1", None, id="delete-task"),
    ],
)
def test_task_mutations_require_authentication(client, method, path, payload):
    response = client.request(method, path, json=payload)

    assert response.status_code == 401
