from contextlib import contextmanager
import os
import sqlite3
from pathlib import Path
from typing import Iterator


def database_path() -> Path:
    return Path(os.getenv("TASKS_DB_PATH", "data/tasks.db"))


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )
            """
        )
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(tasks)")
        }
        if not columns:
            _create_tasks_table(connection)
            return

        current_columns = {
            "id", "title", "description", "status", "created_at", "user_id"
        }
        previous_columns = {"id", "title", "description", "status", "created_at"}
        legacy_columns = {"id", "title", "completed", "created_at"}
        if current_columns.issubset(columns):
            return
        if previous_columns.issubset(columns) and "user_id" not in columns:
            connection.execute(
                "ALTER TABLE tasks ADD COLUMN user_id INTEGER "
                "REFERENCES users(id) ON DELETE SET NULL"
            )
            return
        if legacy_columns.issubset(columns) and "status" not in columns:
            connection.execute("ALTER TABLE tasks RENAME TO tasks_legacy")
            _create_tasks_table(connection)
            connection.execute(
                """
                INSERT INTO tasks (id, title, description, status, created_at)
                SELECT id, title, '', CASE WHEN completed != 0 THEN 'done' ELSE 'todo' END,
                       created_at
                FROM tasks_legacy
                """
            )
            connection.execute("DROP TABLE tasks_legacy")
            return
        raise RuntimeError("The tasks database has an unsupported schema.")


def _create_tasks_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 120),
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'todo'
                CHECK(status IN ('todo', 'in_progress', 'done')),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
        )
        """
    )