"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import pytest

from app import create_app
from app.extensions import db
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.worker import Worker, WorkerStatus
from app.models.task import utcnow


@pytest.fixture()
def app(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    # Forward slashes work on Windows with SQLAlchemy's SQLite URL parser
    monkeypatch.setenv("TEST_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    application = create_app("testing")
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def sample_task(app):
    task = Task(
        task_name="sample_task",
        description="Fixture task",
        priority=TaskPriority.MEDIUM,
        status=TaskStatus.PENDING,
        payload={"type": "CALCULATE", "operation": "sum", "numbers": [1, 2, 3]},
        max_retries=3,
    )
    db.session.add(task)
    db.session.commit()
    return task


@pytest.fixture()
def sample_worker(app):
    worker = Worker(
        worker_name="Test-Worker-1",
        status=WorkerStatus.IDLE,
        last_heartbeat=utcnow(),
    )
    db.session.add(worker)
    db.session.commit()
    return worker
