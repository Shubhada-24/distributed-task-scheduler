"""Worker ORM model."""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class WorkerStatus(enum.StrEnum):
    IDLE = "IDLE"
    BUSY = "BUSY"
    OFFLINE = "OFFLINE"


class Worker(db.Model):
    """A background process that executes scheduled tasks."""

    __tablename__ = "workers"
    __table_args__ = (Index("ix_workers_status", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    worker_name: Mapped[str] = mapped_column(db.String(120), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        db.String(20), nullable=False, default=WorkerStatus.IDLE
    )
    last_heartbeat: Mapped[datetime | None] = mapped_column(db.DateTime)
    tasks_completed: Mapped[int] = mapped_column(db.Integer, nullable=False, default=0)
    tasks_failed: Mapped[int] = mapped_column(db.Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(
        db.DateTime, nullable=False, default=utcnow
    )

    tasks = relationship("Task", back_populates="worker", foreign_keys="Task.worker_id")
    executions = relationship("Execution", back_populates="worker")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "worker_name": self.worker_name,
            "status": self.status,
            "last_heartbeat": (
                self.last_heartbeat.isoformat() + "Z" if self.last_heartbeat else None
            ),
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "started_at": self.started_at.isoformat() + "Z" if self.started_at else None,
        }

    def __repr__(self) -> str:
        return f"<Worker id={self.id} name={self.worker_name!r} status={self.status}>"
