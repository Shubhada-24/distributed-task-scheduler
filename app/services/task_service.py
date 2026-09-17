"""Task business logic."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.execution import Execution
from app.models.task import Task, TaskPriority, TaskStatus
from app.utils.logger import get_logger
from app.utils.validators import ValidationError, validate_task_create

logger = get_logger("app.task_service")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TaskService:
    """CRUD and lifecycle operations for tasks."""

    def create_task(self, data: dict[str, Any]) -> Task:
        validated = validate_task_create(data)
        scheduled_at = validated["scheduled_at"]
        status = TaskStatus.SCHEDULED if scheduled_at and scheduled_at > utcnow() else TaskStatus.PENDING

        task = Task(
            task_name=validated["task_name"],
            description=validated.get("description"),
            priority=int(validated["priority"]),
            status=status,
            payload=validated["payload"],
            scheduled_at=scheduled_at,
            max_retries=validated["max_retries"],
            retry_count=0,
        )
        db.session.add(task)
        db.session.commit()
        logger.info("Task created id=%s name=%s priority=%s status=%s",
                    task.id, task.task_name, task.priority_name, task.status)
        return task

    def get_task(self, task_id: int) -> Task | None:
        return db.session.get(Task, task_id)

    def list_tasks(
        self,
        status: str | None = None,
        priority: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> dict[str, Any]:
        page = max(1, page)
        limit = min(max(1, limit), 100)

        query = select(Task).order_by(Task.created_at.desc())
        if status:
            query = query.where(Task.status == status.upper())
        if priority:
            try:
                priority_value = TaskPriority.from_name(priority)
            except ValueError as exc:
                raise ValidationError(f"Invalid priority filter: {priority}", 422) from exc
            query = query.where(Task.priority == int(priority_value))

        total = db.session.scalar(
            select(db.func.count()).select_from(query.subquery())
        ) or 0
        items = db.session.scalars(
            query.offset((page - 1) * limit).limit(limit)
        ).all()

        return {
            "items": [t.to_dict() for t in items],
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit if total else 0,
        }

    def delete_task(self, task_id: int) -> bool:
        task = self.get_task(task_id)
        if task is None:
            return False
        if task.status == TaskStatus.RUNNING:
            raise ValidationError("Cannot delete a running task. Cancel first if pending.", 409)
        db.session.delete(task)
        db.session.commit()
        logger.info("Task deleted id=%s", task_id)
        return True

    def cancel_task(self, task_id: int) -> Task:
        task = self.get_task(task_id)
        if task is None:
            raise ValidationError("Task not found", 404)
        cancellable = {
            TaskStatus.PENDING,
            TaskStatus.SCHEDULED,
            TaskStatus.RETRYING,
        }
        if task.status not in cancellable:
            raise ValidationError(
                f"Cannot cancel task in status {task.status}.", 409
            )
        task.status = TaskStatus.CANCELLED
        task.completed_at = utcnow()
        db.session.commit()
        logger.info("Task cancelled id=%s", task_id)
        return task

    def retry_task(self, task_id: int) -> Task:
        """Manually re-queue a FAILED task."""
        task = self.get_task(task_id)
        if task is None:
            raise ValidationError("Task not found", 404)
        if task.status != TaskStatus.FAILED:
            raise ValidationError("Only FAILED tasks can be manually retried.", 409)

        task.status = TaskStatus.PENDING
        task.error_message = None
        task.result = None
        task.worker_id = None
        task.started_at = None
        task.completed_at = None
        task.scheduled_at = None
        # Manual retry resets the automatic retry counter so the user gets a fresh budget
        task.retry_count = 0
        db.session.commit()
        logger.info("Task manually queued for retry id=%s", task_id)
        return task

    def get_executions(self, task_id: int) -> list[dict[str, Any]]:
        task = self.get_task(task_id)
        if task is None:
            raise ValidationError("Task not found", 404)
        executions = db.session.scalars(
            select(Execution)
            .where(Execution.task_id == task_id)
            .order_by(Execution.started_at.desc())
        ).all()
        return [e.to_dict() for e in executions]

    def get_stats(self) -> dict[str, int]:
        from app.models.worker import Worker, WorkerStatus

        def count_status(status: str) -> int:
            return db.session.scalar(
                select(db.func.count()).select_from(Task).where(Task.status == status)
            ) or 0

        total = db.session.scalar(select(db.func.count()).select_from(Task)) or 0
        active_workers = db.session.scalar(
            select(db.func.count())
            .select_from(Worker)
            .where(Worker.status.in_([WorkerStatus.IDLE, WorkerStatus.BUSY]))
        ) or 0

        return {
            "total_tasks": total,
            "pending_tasks": count_status(TaskStatus.PENDING)
            + count_status(TaskStatus.SCHEDULED)
            + count_status(TaskStatus.RETRYING),
            "running_tasks": count_status(TaskStatus.RUNNING),
            "completed_tasks": count_status(TaskStatus.COMPLETED),
            "failed_tasks": count_status(TaskStatus.FAILED),
            "cancelled_tasks": count_status(TaskStatus.CANCELLED),
            "active_workers": active_workers,
        }
