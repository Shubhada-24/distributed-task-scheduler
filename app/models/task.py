"""Task ORM model and related enumerations."""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import Index, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TaskPriority(enum.IntEnum):
    """Numeric priorities — higher value means higher precedence."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @classmethod
    def from_name(cls, name: str) -> "TaskPriority":
        try:
            return cls[name.upper()]
        except KeyError as exc:
            raise ValueError(f"Invalid priority: {name}") from exc


class TaskStatus(enum.StrEnum):
    PENDING = "PENDING"
    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    RETRYING = "RETRYING"


class Task(db.Model):
    """A unit of work managed by the scheduler and executed by workers."""

    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_priority", "priority"),
        Index("ix_tasks_scheduled_at", "scheduled_at"),
        Index("ix_tasks_status_priority", "status", "priority"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_name: Mapped[str] = mapped_column(db.String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(db.String(500))
    priority: Mapped[int] = mapped_column(
        db.Integer, nullable=False, default=TaskPriority.MEDIUM
    )
    status: Mapped[str] = mapped_column(
        db.String(20), nullable=False, default=TaskStatus.PENDING
    )
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime, nullable=False, default=utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(db.DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(db.DateTime)
    retry_count: Mapped[int] = mapped_column(db.Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(db.Integer, nullable=False, default=3)
    worker_id: Mapped[int | None] = mapped_column(
        db.ForeignKey("workers.id"), nullable=True
    )
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text)

    worker = relationship("Worker", back_populates="tasks", foreign_keys=[worker_id])
    executions = relationship(
        "Execution", back_populates="task", cascade="all, delete-orphan"
    )

    @property
    def priority_name(self) -> str:
        try:
            return TaskPriority(self.priority).name
        except ValueError:
            return str(self.priority)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_name": self.task_name,
            "description": self.description,
            "priority": self.priority_name,
            "priority_value": self.priority,
            "status": self.status,
            "payload": self.payload,
            "scheduled_at": self.scheduled_at.isoformat() + "Z" if self.scheduled_at else None,
            "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
            "started_at": self.started_at.isoformat() + "Z" if self.started_at else None,
            "completed_at": self.completed_at.isoformat() + "Z" if self.completed_at else None,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "worker_id": self.worker_id,
            "result": self.result,
            "error_message": self.error_message,
        }

    def __repr__(self) -> str:
        return f"<Task id={self.id} name={self.task_name!r} status={self.status}>"
