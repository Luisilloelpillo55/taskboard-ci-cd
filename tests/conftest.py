import pytest
from starlette.testclient import TestClient

from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TASKS_DB_PATH", str(tmp_path / "test-tasks.db"))
    with TestClient(app) as test_client:
        yield test_client