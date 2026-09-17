"""Seed the database with sample workers and tasks for demos."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow running as `python scripts/seed.py` from project root
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app import create_app
from app.extensions import db
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.worker import Worker, WorkerStatus
from app.models.task import utcnow


def seed() -> None:
    app = create_app(os.getenv("FLASK_ENV", "development"))
    # Stop runtime threads immediately — seed only needs DB access
    runtime = app.extensions.get("runtime")
    if runtime:
        runtime.scheduler.stop()
        runtime.worker_service.stop()

    with app.app_context():
        db.create_all()

        if not db.session.query(Worker).count():
            for i in range(1, 4):
                db.session.add(
                    Worker(
                        worker_name=f"Seed-Worker-{i}",
                        status=WorkerStatus.OFFLINE,
                        last_heartbeat=utcnow(),
                    )
                )

        samples = [
            Task(
                task_name="welcome_email",
                description="Send welcome email",
                priority=TaskPriority.HIGH,
                status=TaskStatus.COMPLETED,
                payload={
                    "type": "SEND_NOTIFICATION",
                    "email": "alice@example.com",
                    "message": "Welcome!",
                },
                result={"delivered": True},
                max_retries=3,
                completed_at=utcnow(),
            ),
            Task(
                task_name="sum_report",
                description="Calculate totals",
                priority=TaskPriority.MEDIUM,
                status=TaskStatus.PENDING,
                payload={"type": "CALCULATE", "operation": "sum", "numbers": [5, 10, 15]},
                max_retries=3,
            ),
            Task(
                task_name="critical_ingest",
                description="High priority processing",
                priority=TaskPriority.CRITICAL,
                status=TaskStatus.PENDING,
                payload={
                    "type": "DATA_PROCESSING",
                    "operation": "unique",
                    "items": ["a", "b", "a", "c"],
                },
                max_retries=2,
            ),
            Task(
                task_name="failing_job",
                description="Demonstrates failure + retry",
                priority=TaskPriority.LOW,
                status=TaskStatus.FAILED,
                payload={"type": "FAIL", "reason": "Seeded failure example"},
                error_message="Seeded failure example",
                retry_count=3,
                max_retries=3,
                completed_at=utcnow(),
            ),
        ]
        for task in samples:
            db.session.add(task)

        db.session.commit()
        print("Seed complete: workers + sample tasks inserted.")


if __name__ == "__main__":
    seed()
