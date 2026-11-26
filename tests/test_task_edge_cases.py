import pytest


def register(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "task-owner@example.com", "password": "GoodPassphrase2026!"},
    )
    assert response.status_code == 201


@pytest.mark.parametrize("title_length", [1, 120], ids=["minimum", "maximum"])
def test_task_title_length_boundaries(client, title_length):
    register(client)

    response = client.post("/api/tasks", json={"title": "t" * title_length})

    assert response.status_code == 201
    assert len(response.json()["title"]) == title_length


@pytest.mark.parametrize("description_length", [0, 500], ids=["empty", "maximum"])
def test_task_description_length_boundaries(client, description_length):
    register(client)

    response = client.post(
        "/api/tasks",
        json={"title": "Description boundary", "description": "d" * description_length},
    )

    assert response.status_code == 201
    assert len(response.json()["description"]) == description_length


def test_task_creation_defaults_an_omitted_description_to_empty(client):
    register(client)

    response = client.post("/api/tasks", json={"title": "No description"})

    assert response.status_code == 201
    assert response.json()["description"] == ""


def test_task_creation_trims_title_and_description(client):
    register(client)

    response = client.post(
        "/api/tasks",
        json={"title": "  Trimmed title  ", "description": "  Trimmed details  "},
    )

    assert response.status_code == 201
    assert response.json()["title"] == "Trimmed title"
    assert response.json()["description"] == "Trimmed details"


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({}, id="missing-title"),
        pytest.param({"title": None}, id="null-title"),
        pytest.param({"title": ""}, id="empty-title"),
        pytest.param(
            {"title": "Valid title", "description": None},
            id="null-description",
        ),
        pytest.param(
            {"title": "Valid title", "description": "d" * 501},
            id="description-too-long",
        ),
    ],
)
def test_task_creation_rejects_invalid_payloads(client, payload):
    register(client)

    assert client.post("/api/tasks", json=payload).status_code == 422


def test_task_list_is_ordered_newest_first(client):
    register(client)
    for title in ("First", "Second", "Third"):
        assert client.post("/api/tasks", json={"title": title}).status_code == 201

    response = client.get("/api/tasks")

    assert response.status_code == 200
    assert [task["title"] for task in response.json()] == ["Third", "Second", "First"]


@pytest.mark.parametrize("task_status", ["todo", "in_progress", "done"])
def test_task_update_accepts_each_documented_status(client, task_status):
    register(client)
    task = client.post("/api/tasks", json={"title": "Status test"}).json()

    response = client.patch(
        f"/api/tasks/{task['id']}", json={"status": task_status}
    )

    assert response.status_code == 200
    assert response.json()["status"] == task_status


def test_task_update_trims_text_and_preserves_omitted_fields(client):
    register(client)
    created = client.post(
        "/api/tasks",
        json={"title": "Original title", "description": "Original details"},
    ).json()

    response = client.patch(
        f"/api/tasks/{created['id']}",
        json={"title": "  Updated title  ", "description": "  Updated details  "},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated title"
    assert response.json()["description"] == "Updated details"
    assert response.json()["status"] == "todo"
    assert response.json()["created_at"] == created["created_at"]


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"title": None}, id="null-title"),
        pytest.param({"description": None}, id="null-description"),
        pytest.param({"title": "  "}, id="blank-title"),
        pytest.param({"title": "t" * 121}, id="title-too-long"),
        pytest.param({"description": "d" * 501}, id="description-too-long"),
        pytest.param({"status": "blocked"}, id="unknown-status"),
        pytest.param({"unexpected": "field"}, id="unexpected-field"),
    ],
)
def test_task_update_rejects_invalid_payloads(client, payload):
    register(client)
    task = client.post("/api/tasks", json={"title": "Valid task"}).json()

    response = client.patch(f"/api/tasks/{task['id']}", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("method", "path"),
    [
        pytest.param("PATCH", "/api/tasks/not-an-integer", id="update"),
        pytest.param("DELETE", "/api/tasks/not-an-integer", id="delete"),
    ],
)
def test_task_routes_reject_non_integer_ids(client, method, path):
    register(client)

    assert client.request(method, path, json={"status": "done"}).status_code == 422
