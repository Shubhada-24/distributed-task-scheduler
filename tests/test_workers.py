"""Worker execution and retry tests."""

from __future__ import annotations

import time
from datetime import datetime

from app.executors import TaskExecutionError, TaskExecutor
from app.extensions import db
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.worker import WorkerStatus
from app.scheduler.priority_queue import PriorityTaskQueue
from app.services.retry_service import RetryService
from app.services.worker_service import WorkerRuntime, WorkerService


def test_executor_calculate():
    result = TaskExecutor().execute(
        {"type": "CALCULATE", "operation": "sum", "numbers": [10, 20, 30]}
    )
    assert result["result"] == 60


def test_executor_unknown_type():
    try:
        TaskExecutor().execute({"type": "SHELL", "cmd": "rm -rf /"})
        assert False, "should have raised"
    except TaskExecutionError:
        pass


def test_executor_fail():
    try:
        TaskExecutor().execute({"type": "FAIL", "reason": "boom"})
        assert False
    except TaskExecutionError as exc:
        assert "boom" in str(exc)


def test_retry_backoff_and_limit(app, sample_task):
    retry = RetryService()
    sample_task.max_retries = 2
    sample_task.retry_count = 0

    assert retry.should_retry(sample_task)
    assert retry.schedule_retry(sample_task) is True
    assert sample_task.status == TaskStatus.RETRYING
    assert sample_task.retry_count == 1
    assert retry.backoff_seconds(1) == 2

    assert retry.schedule_retry(sample_task) is True
    assert sample_task.retry_count == 2

    assert retry.schedule_retry(sample_task) is False
    assert sample_task.status == TaskStatus.FAILED


def test_worker_executes_task(app):
    task = Task(
        task_name="calc",
        priority=TaskPriority.HIGH,
        status=TaskStatus.PENDING,
        payload={"type": "CALCULATE", "operation": "sum", "numbers": [4, 5]},
        max_retries=1,
        created_at=datetime.utcnow(),
    )
    db.session.add(task)
    db.session.commit()
    task_id = task.id

    queue = PriorityTaskQueue()
    queue.push(task_id, task.priority, task.created_at, payload=task.payload)

    worker = WorkerRuntime(
        app=app,
        worker_name="Unit-Worker",
        task_queue=queue,
        heartbeat_interval=0.2,
        poll_interval=0.05,
    )
    worker.start()
    deadline = time.time() + 5
    while time.time() < deadline:
        db.session.expire_all()
        refreshed = db.session.get(Task, task_id)
        if refreshed.status == TaskStatus.COMPLETED:
            break
        time.sleep(0.1)
    worker.stop()

    refreshed = db.session.get(Task, task_id)
    assert refreshed.status == TaskStatus.COMPLETED
    assert refreshed.result["result"] == 9
    assert refreshed.worker_id is not None


def test_worker_failure_retries(app):
    task = Task(
        task_name="fail_me",
        priority=TaskPriority.MEDIUM,
        status=TaskStatus.PENDING,
        payload={"type": "FAIL", "reason": "nope"},
        max_retries=1,
        created_at=datetime.utcnow(),
    )
    db.session.add(task)
    db.session.commit()
    task_id = task.id

    queue = PriorityTaskQueue()
    queue.push(task_id, task.priority, task.created_at)

    worker = WorkerRuntime(
        app=app,
        worker_name="Fail-Worker",
        task_queue=queue,
        heartbeat_interval=0.2,
        poll_interval=0.05,
    )
    worker.start()
    deadline = time.time() + 5
    while time.time() < deadline:
        db.session.expire_all()
        refreshed = db.session.get(Task, task_id)
        if refreshed.status in (TaskStatus.RETRYING, TaskStatus.FAILED):
            break
        time.sleep(0.1)
    worker.stop()

    refreshed = db.session.get(Task, task_id)
    assert refreshed.status == TaskStatus.RETRYING
    assert refreshed.retry_count == 1
    assert refreshed.error_message == "nope"


def test_claim_is_exclusive(app, sample_task):
    queue = PriorityTaskQueue()
    w1 = WorkerRuntime(app, "W1", queue)
    w2 = WorkerRuntime(app, "W2", queue)
    with app.app_context():
        w1._register()
        w2._register()
        assert w1._claim_task(sample_task.id) is True
        assert w2._claim_task(sample_task.id) is False
