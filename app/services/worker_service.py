"""Worker registration, heartbeats, and concurrent task execution."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select, update

from app.executors import TaskExecutionError, TaskExecutor
from app.extensions import db
from app.models.execution import Execution, ExecutionStatus
from app.models.task import Task, TaskStatus
from app.models.worker import Worker, WorkerStatus
from app.scheduler.priority_queue import PriorityTaskQueue
from app.services.retry_service import RetryService
from app.utils.logger import get_logger

if TYPE_CHECKING:
    from flask import Flask

logger = get_logger("worker")

# Serializes ORM access across worker + heartbeat threads (important for SQLite).
_DB_LOCK = threading.RLock()


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class WorkerRuntime:
    """One concurrent worker thread with DB registration and heartbeat."""

    def __init__(
        self,
        app: "Flask",
        worker_name: str,
        task_queue: PriorityTaskQueue,
        heartbeat_interval: float = 5.0,
        poll_interval: float = 0.5,
    ) -> None:
        self.app = app
        self.worker_name = worker_name
        self.task_queue = task_queue
        self.heartbeat_interval = heartbeat_interval
        self.poll_interval = poll_interval
        self.executor = TaskExecutor()
        self.retry_service = RetryService()
        self.worker_id: int | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._heartbeat_thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop_event.clear()
        with self.app.app_context():
            self._register()
        self._thread = threading.Thread(
            target=self._run,
            name=self.worker_name,
            daemon=True,
        )
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"{self.worker_name}-heartbeat",
            daemon=True,
        )
        self._thread.start()
        self._heartbeat_thread.start()
        logger.info("Worker %s started", self.worker_name)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=timeout)
        with self.app.app_context():
            self._mark_offline()
        logger.info("Worker %s stopped", self.worker_name)

    def _register(self) -> None:
        with _DB_LOCK:
            worker = db.session.scalar(
                select(Worker).where(Worker.worker_name == self.worker_name)
            )
            if worker is None:
                worker = Worker(
                    worker_name=self.worker_name,
                    status=WorkerStatus.IDLE,
                    last_heartbeat=utcnow(),
                    started_at=utcnow(),
                )
                db.session.add(worker)
            else:
                worker.status = WorkerStatus.IDLE
                worker.last_heartbeat = utcnow()
                worker.started_at = utcnow()
            db.session.commit()
            self.worker_id = worker.id

    def _mark_offline(self) -> None:
        if self.worker_id is None:
            return
        with _DB_LOCK:
            db.session.execute(
                update(Worker)
                .where(Worker.id == self.worker_id)
                .values(status=WorkerStatus.OFFLINE, last_heartbeat=utcnow())
            )
            db.session.commit()

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                with self.app.app_context():
                    if self.worker_id is not None:
                        with _DB_LOCK:
                            db.session.execute(
                                update(Worker)
                                .where(
                                    Worker.id == self.worker_id,
                                    Worker.status != WorkerStatus.OFFLINE,
                                )
                                .values(last_heartbeat=utcnow())
                            )
                            db.session.commit()
            except Exception:
                logger.exception("Heartbeat failed for %s", self.worker_name)
            self._stop_event.wait(self.heartbeat_interval)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            entry = self.task_queue.pop()
            if entry is None:
                self._stop_event.wait(self.poll_interval)
                continue
            try:
                with self.app.app_context():
                    self._process_task(entry.task_id)
            except Exception:
                logger.exception(
                    "Unhandled error processing task id=%s on %s",
                    entry.task_id,
                    self.worker_name,
                )

    def _process_task(self, task_id: int) -> None:
        with _DB_LOCK:
            claimed = self._claim_task(task_id)
            if not claimed:
                logger.debug(
                    "Task id=%s already claimed or not eligible; skipping", task_id
                )
                return

            task = db.session.get(Task, task_id)
            if task is None or self.worker_id is None:
                return

            db.session.execute(
                update(Worker)
                .where(Worker.id == self.worker_id)
                .values(status=WorkerStatus.BUSY)
            )
            execution = Execution(
                task_id=task.id,
                worker_id=self.worker_id,
                status=ExecutionStatus.RUNNING,
                started_at=utcnow(),
            )
            db.session.add(execution)
            db.session.commit()
            execution_id = execution.id
            payload = dict(task.payload or {})
            task_name = task.task_name

        logger.info(
            "Task started id=%s name=%s on worker=%s",
            task_id,
            task_name,
            self.worker_name,
        )

        start = time.perf_counter()
        try:
            # Execute outside the DB lock so other workers can claim concurrently (MySQL).
            result = self.executor.execute(payload)
            duration = time.perf_counter() - start
            with _DB_LOCK:
                self._mark_success(task_id, execution_id, result, duration)
            logger.info(
                "Task completed id=%s duration=%.3fs worker=%s",
                task_id,
                duration,
                self.worker_name,
            )
        except TaskExecutionError as exc:
            duration = time.perf_counter() - start
            with _DB_LOCK:
                self._mark_failure(task_id, execution_id, duration, str(exc))
        except Exception as exc:
            duration = time.perf_counter() - start
            with _DB_LOCK:
                self._mark_failure(
                    task_id, execution_id, duration, f"Unexpected error: {exc}"
                )

    def _claim_task(self, task_id: int) -> bool:
        """Atomically transition an eligible task to RUNNING.

        Uses a conditional UPDATE so only one worker can claim a given task.
        Caller must hold ``_DB_LOCK``.
        """
        now = utcnow()
        stmt = (
            update(Task)
            .where(
                Task.id == task_id,
                Task.status.in_(
                    [TaskStatus.PENDING, TaskStatus.SCHEDULED, TaskStatus.RETRYING]
                ),
            )
            .values(
                status=TaskStatus.RUNNING,
                worker_id=self.worker_id,
                started_at=now,
                error_message=None,
            )
        )
        result = db.session.execute(stmt)
        db.session.commit()
        return result.rowcount == 1

    def _mark_success(
        self,
        task_id: int,
        execution_id: int,
        result: dict,
        duration: float,
    ) -> None:
        now = utcnow()
        db.session.execute(
            update(Task)
            .where(Task.id == task_id)
            .values(
                status=TaskStatus.COMPLETED,
                result=result,
                error_message=None,
                completed_at=now,
            )
        )
        db.session.execute(
            update(Execution)
            .where(Execution.id == execution_id)
            .values(
                status=ExecutionStatus.COMPLETED,
                result=result,
                completed_at=now,
                duration=duration,
            )
        )
        db.session.execute(
            update(Worker)
            .where(Worker.id == self.worker_id)
            .values(
                status=WorkerStatus.IDLE,
                tasks_completed=Worker.tasks_completed + 1,
            )
        )
        db.session.commit()

    def _mark_failure(
        self,
        task_id: int,
        execution_id: int,
        duration: float,
        error_message: str,
    ) -> None:
        now = utcnow()
        task = db.session.get(Task, task_id)
        if task is None:
            return

        db.session.execute(
            update(Execution)
            .where(Execution.id == execution_id)
            .values(
                status=ExecutionStatus.FAILED,
                error_message=error_message,
                completed_at=now,
                duration=duration,
            )
        )
        task.error_message = error_message
        retried = self.retry_service.schedule_retry(task)
        db.session.execute(
            update(Worker)
            .where(Worker.id == self.worker_id)
            .values(
                status=WorkerStatus.IDLE,
                tasks_failed=Worker.tasks_failed + 1,
            )
        )
        db.session.commit()
        logger.warning(
            "Task failed id=%s error=%s retried=%s worker=%s",
            task_id,
            error_message,
            retried,
            self.worker_name,
        )


class WorkerService:
    """Manages a pool of WorkerRuntime instances."""

    def __init__(
        self,
        app: "Flask",
        task_queue: PriorityTaskQueue,
        num_workers: int = 3,
        heartbeat_interval: float = 5.0,
    ) -> None:
        self.app = app
        self.task_queue = task_queue
        self.num_workers = num_workers
        self.heartbeat_interval = heartbeat_interval
        self._workers: list[WorkerRuntime] = []
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._workers:
                return
            for i in range(1, self.num_workers + 1):
                runtime = WorkerRuntime(
                    app=self.app,
                    worker_name=f"Worker-{i}",
                    task_queue=self.task_queue,
                    heartbeat_interval=self.heartbeat_interval,
                )
                runtime.start()
                self._workers.append(runtime)
            logger.info("Started %s workers", self.num_workers)

    def stop(self) -> None:
        with self._lock:
            workers = list(self._workers)
            self._workers.clear()
        for w in workers:
            w.stop()

    def list_workers(self) -> list[dict]:
        workers = db.session.scalars(select(Worker).order_by(Worker.id)).all()
        return [w.to_dict() for w in workers]

    def get_worker(self, worker_id: int) -> Worker | None:
        return db.session.get(Worker, worker_id)
