"""Priority queue and scheduler tests."""

from __future__ import annotations

from datetime import datetime, timedelta
import time

from app.extensions import db
from app.models.task import Task, TaskPriority, TaskStatus
from app.scheduler.priority_queue import PriorityTaskQueue
from app.services.scheduler_service import SchedulerService, SchedulerState


def test_priority_ordering():
    q = PriorityTaskQueue()
    now = datetime.utcnow()
    q.push(1, TaskPriority.LOW, now)
    q.push(2, TaskPriority.CRITICAL, now)
    q.push(3, TaskPriority.HIGH, now)
    assert q.pop().task_id == 2
    assert q.pop().task_id == 3
    assert q.pop().task_id == 1


def test_same_priority_fifo():
    q = PriorityTaskQueue()
    t1 = datetime(2026, 1, 1, 10, 0, 0)
    t2 = datetime(2026, 1, 1, 10, 0, 1)
    t3 = datetime(2026, 1, 1, 10, 0, 2)
    q.push(10, TaskPriority.HIGH, t2)
    q.push(11, TaskPriority.HIGH, t1)
    q.push(12, TaskPriority.HIGH, t3)
    assert [q.pop().task_id for _ in range(3)] == [11, 10, 12]


def test_remove_and_size():
    q = PriorityTaskQueue()
    now = datetime.utcnow()
    q.push(1, 3, now)
    q.push(2, 2, now)
    assert q.size() == 2
    assert q.remove(1) is True
    assert q.contains(1) is False
    assert q.size() == 1
    assert q.peek().task_id == 2
    assert q.is_empty() is False
    q.pop()
    assert q.is_empty() is True


def test_scheduler_enqueues_due_tasks(app):
    past = datetime.utcnow() - timedelta(seconds=5)
    future = datetime.utcnow() + timedelta(hours=2)

    due = Task(
        task_name="due",
        priority=TaskPriority.HIGH,
        status=TaskStatus.SCHEDULED,
        scheduled_at=past,
        payload={"type": "CALCULATE", "operation": "sum", "numbers": [1]},
    )
    waiting = Task(
        task_name="waiting",
        priority=TaskPriority.CRITICAL,
        status=TaskStatus.SCHEDULED,
        scheduled_at=future,
        payload={"type": "CALCULATE", "operation": "sum", "numbers": [1]},
    )
    db.session.add_all([due, waiting])
    db.session.commit()

    queue = PriorityTaskQueue()
    scheduler = SchedulerService(app, queue, poll_interval=0.05)
    with app.app_context():
        scheduler._enqueue_eligible_tasks()

    assert queue.contains(due.id)
    assert not queue.contains(waiting.id)
    assert queue.peek().task_id == due.id


def test_scheduler_start_stop(app):
    queue = PriorityTaskQueue()
    scheduler = SchedulerService(app, queue, poll_interval=0.05)
    scheduler.start()
    time.sleep(0.15)
    assert scheduler.state == SchedulerState.RUNNING
    scheduler.stop()
    assert scheduler.state == SchedulerState.STOPPED
