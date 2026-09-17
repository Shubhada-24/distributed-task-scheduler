"""Unit tests for task service and validation."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.extensions import db
from app.models.task import TaskStatus
from app.services.task_service import TaskService
from app.utils.validators import ValidationError, validate_task_create
import pytest


def test_create_task_success(app):
    service = TaskService()
    task = service.create_task(
        {
            "task_name": "send_email",
            "description": "Welcome",
            "priority": "HIGH",
            "payload": {"type": "SEND_NOTIFICATION", "email": "a@b.com"},
            "max_retries": 2,
        }
    )
    assert task.id is not None
    assert task.status == TaskStatus.PENDING
    assert task.priority_name == "HIGH"


def test_create_scheduled_task(app):
    service = TaskService()
    future = (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"
    task = service.create_task(
        {
            "task_name": "future_job",
            "priority": "LOW",
            "scheduled_at": future,
            "payload": {"type": "DELAY", "seconds": 1},
        }
    )
    assert task.status == TaskStatus.SCHEDULED
    assert task.scheduled_at is not None


def test_invalid_task_missing_name():
    with pytest.raises(ValidationError) as exc:
        validate_task_create({"priority": "HIGH"})
    assert exc.value.status_code == 400


def test_invalid_priority():
    with pytest.raises(ValidationError):
        validate_task_create({"task_name": "x", "priority": "ULTRA"})


def test_invalid_max_retries():
    with pytest.raises(ValidationError):
        validate_task_create({"task_name": "x", "max_retries": -1})


def test_cancel_and_retry(app, sample_task):
    service = TaskService()
    cancelled = service.cancel_task(sample_task.id)
    assert cancelled.status == TaskStatus.CANCELLED

    with pytest.raises(ValidationError):
        service.retry_task(sample_task.id)

    sample_task.status = TaskStatus.FAILED
    db.session.commit()
    retried = service.retry_task(sample_task.id)
    assert retried.status == TaskStatus.PENDING
    assert retried.retry_count == 0


def test_delete_running_forbidden(app, sample_task):
    service = TaskService()
    sample_task.status = TaskStatus.RUNNING
    db.session.commit()
    with pytest.raises(ValidationError) as exc:
        service.delete_task(sample_task.id)
    assert exc.value.status_code == 409
