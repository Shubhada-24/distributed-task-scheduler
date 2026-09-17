"""Execution history ORM model."""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import Index, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ExecutionStatus(enum.StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Execution(db.Model):
    """One attempt to run a task on a worker."""

    __tablename__ = "executions"
    __table_args__ = (
        Index("ix_executions_task_id", "task_id"),
        Index("ix_executions_worker_id", "worker_id"),
        Index("ix_executions_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        db.ForeignKey("tasks.id"), nullable=False
    )
    worker_id: Mapped[int | None] = mapped_column(
        db.ForeignKey("workers.id"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        db.DateTime, nullable=False, default=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(db.DateTime)
    status: Mapped[str] = mapped_column(
        db.String(20), nullable=False, default=ExecutionStatus.RUNNING
    )
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    duration: Mapped[float | None] = mapped_column(db.Float)

    task = relationship("Task", back_populates="executions")
    worker = relationship("Worker", back_populates="executions")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "worker_id": self.worker_id,
            "started_at": self.started_at.isoformat() + "Z" if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() + "Z" if self.completed_at else None
            ),
            "status": self.status,
            "result": self.result,
            "error_message": self.error_message,
            "duration": self.duration,
        }

    def __repr__(self) -> str:
        return f"<Execution id={self.id} task_id={self.task_id} status={self.status}>"
