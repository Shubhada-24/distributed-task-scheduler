"""Retry policy with exponential backoff."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.task import Task, TaskStatus
from app.utils.logger import get_logger

logger = get_logger("app.retry_service")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class RetryService:
    """Decide whether a failed task should be retried and when.

    Backoff formula:
        delay_seconds = 2 ** retry_count

    Example with max_retries=3:
        Attempt 1 fails → retry_count becomes 1, schedule after 2^1 = 2s (RETRYING)
        Attempt 2 fails → retry_count becomes 2, schedule after 2^2 = 4s (RETRYING)
        Attempt 3 fails → retry_count becomes 3, schedule after 2^3 = 8s (RETRYING)
        Attempt 4 fails → retry_count == max_retries → FAILED permanently
    """

    def should_retry(self, task: Task) -> bool:
        return task.retry_count < task.max_retries

    def backoff_seconds(self, retry_count: int) -> int:
        return 2 ** retry_count

    def schedule_retry(self, task: Task) -> bool:
        """Increment retry_count and schedule next attempt if allowed.

        Returns True if a retry was scheduled, False if permanently failed.
        """
        if not self.should_retry(task):
            task.status = TaskStatus.FAILED
            task.completed_at = utcnow()
            logger.info(
                "Task id=%s permanently FAILED after %s retries",
                task.id,
                task.retry_count,
            )
            return False

        task.retry_count += 1
        delay = self.backoff_seconds(task.retry_count)
        task.status = TaskStatus.RETRYING
        task.scheduled_at = utcnow() + timedelta(seconds=delay)
        task.worker_id = None
        task.started_at = None
        task.completed_at = None
        logger.info(
            "Task id=%s RETRYING attempt=%s/%s backoff=%ss scheduled_at=%s",
            task.id,
            task.retry_count,
            task.max_retries,
            delay,
            task.scheduled_at.isoformat(),
        )
        return True
