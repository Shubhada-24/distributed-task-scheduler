"""Background scheduler that feeds the priority queue and dispatches work."""

from __future__ import annotations

import enum
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import or_, select

from app.extensions import db
from app.models.task import Task, TaskStatus
from app.scheduler.priority_queue import PriorityTaskQueue
from app.utils.logger import get_logger

if TYPE_CHECKING:
    from flask import Flask

logger = get_logger("scheduler")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SchedulerState(enum.StrEnum):
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"


class SchedulerService:
    """Poll the database for eligible tasks and push them onto the priority queue.

    Workers then pop from the shared queue. Database claim (PENDING → RUNNING)
    happens inside the worker with a conditional UPDATE for safety.
    """

    def __init__(
        self,
        app: "Flask",
        task_queue: PriorityTaskQueue,
        poll_interval: float = 1.0,
    ) -> None:
        self.app = app
        self.task_queue = task_queue
        self.poll_interval = poll_interval
        self._state = SchedulerState.STOPPED
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> SchedulerState:
        return self._state

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                logger.warning("Scheduler already running")
                return
            self._state = SchedulerState.STARTING
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="SchedulerThread",
                daemon=True,
            )
            self._thread.start()
            logger.info("Scheduler started")

    def stop(self, timeout: float = 5.0) -> None:
        with self._lock:
            self._stop_event.set()
            thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=timeout)
        self._state = SchedulerState.STOPPED
        logger.info("Scheduler stopped")

    def _run(self) -> None:
        self._state = SchedulerState.RUNNING
        while not self._stop_event.is_set():
            try:
                with self.app.app_context():
                    self._enqueue_eligible_tasks()
            except Exception:
                logger.exception("Scheduler loop error")
            self._stop_event.wait(self.poll_interval)

    def _enqueue_eligible_tasks(self) -> None:
        """Load pending/scheduled/retrying tasks that are due and push to the queue."""
        now = utcnow()
        stmt = (
            select(Task)
            .where(
                Task.status.in_(
                    [TaskStatus.PENDING, TaskStatus.SCHEDULED, TaskStatus.RETRYING]
                )
            )
            .where(or_(Task.scheduled_at.is_(None), Task.scheduled_at <= now))
            .order_by(Task.priority.desc(), Task.created_at.asc())
        )
        tasks = db.session.scalars(stmt).all()
        for task in tasks:
            if self.task_queue.contains(task.id):
                continue
            # Future-scheduled tasks stay out of the queue until due
            if task.scheduled_at and task.scheduled_at > now:
                continue
            self.task_queue.push(
                task_id=task.id,
                priority=task.priority,
                created_at=task.created_at,
                scheduled_at=task.scheduled_at,
                payload=task.payload,
            )
            if task.status == TaskStatus.SCHEDULED:
                task.status = TaskStatus.PENDING
            logger.debug("Enqueued task id=%s priority=%s", task.id, task.priority)
        db.session.commit()

    def sync_cancel(self, task_id: int) -> None:
        """Remove a cancelled task from the in-memory queue if present."""
        self.task_queue.remove(task_id)
