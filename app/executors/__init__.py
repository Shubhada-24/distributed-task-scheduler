"""Safe, predefined task executors — no eval() or shell execution."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any


class TaskExecutionError(Exception):
    """Raised when a predefined task fails in a controlled way."""


class BaseExecutor(ABC):
    """Strategy interface for task execution."""

    @abstractmethod
    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class CalculateExecutor(BaseExecutor):
    """Perform simple arithmetic on a list of numbers."""

    OPERATIONS = {
        "sum": sum,
        "min": min,
        "max": max,
        "avg": lambda nums: sum(nums) / len(nums) if nums else 0,
        "product": lambda nums: _product(nums),
    }

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        operation = str(payload.get("operation", "sum")).lower()
        numbers = payload.get("numbers")
        if not isinstance(numbers, list) or not numbers:
            raise TaskExecutionError("CALCULATE requires a non-empty 'numbers' list.")
        if not all(isinstance(n, (int, float)) and not isinstance(n, bool) for n in numbers):
            raise TaskExecutionError("All numbers must be integers or floats.")
        if operation not in self.OPERATIONS:
            raise TaskExecutionError(
                f"Unsupported operation '{operation}'. "
                f"Allowed: {', '.join(sorted(self.OPERATIONS))}."
            )
        result = self.OPERATIONS[operation](numbers)
        return {"operation": operation, "numbers": numbers, "result": result}


class DelayExecutor(BaseExecutor):
    """Sleep for a bounded number of seconds (demo / load testing)."""

    MAX_SECONDS = 30

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        seconds = payload.get("seconds", 1)
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
            raise TaskExecutionError("'seconds' must be a number.")
        if seconds < 0 or seconds > self.MAX_SECONDS:
            raise TaskExecutionError(
                f"'seconds' must be between 0 and {self.MAX_SECONDS}."
            )
        time.sleep(float(seconds))
        return {"delayed_seconds": float(seconds), "status": "ok"}


class DataProcessingExecutor(BaseExecutor):
    """Transform a list of records with safe built-in operations."""

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        items = payload.get("items")
        operation = str(payload.get("operation", "count")).lower()
        if not isinstance(items, list):
            raise TaskExecutionError("DATA_PROCESSING requires an 'items' list.")

        if operation == "count":
            return {"operation": operation, "result": len(items)}
        if operation == "unique":
            # Preserve order of first occurrence for hashable items
            seen: list[Any] = []
            for item in items:
                if item not in seen:
                    seen.append(item)
            return {"operation": operation, "result": seen, "count": len(seen)}
        if operation == "sort":
            try:
                sorted_items = sorted(items)
            except TypeError as exc:
                raise TaskExecutionError("Items are not sortable.") from exc
            return {"operation": operation, "result": sorted_items}
        if operation == "filter_truthy":
            filtered = [i for i in items if i]
            return {"operation": operation, "result": filtered, "count": len(filtered)}
        raise TaskExecutionError(
            "Unsupported DATA_PROCESSING operation. "
            "Allowed: count, unique, sort, filter_truthy."
        )


class SendNotificationExecutor(BaseExecutor):
    """Simulate sending a notification (no external network calls)."""

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        recipient = payload.get("recipient") or payload.get("email")
        message = payload.get("message", "Notification")
        channel = payload.get("channel", "email")
        if not recipient or not isinstance(recipient, str):
            raise TaskExecutionError(
                "SEND_NOTIFICATION requires a 'recipient' or 'email' string."
            )
        if payload.get("force_fail"):
            raise TaskExecutionError("Simulated notification failure (force_fail=true).")
        return {
            "channel": channel,
            "recipient": recipient,
            "message": message,
            "delivered": True,
        }


class FailExecutor(BaseExecutor):
    """Deterministically fail — useful for retry demos and tests."""

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        reason = payload.get("reason", "Intentional failure for retry demonstration.")
        raise TaskExecutionError(str(reason))


def _product(numbers: list[float]) -> float:
    result = 1.0
    for n in numbers:
        result *= n
    return result


class TaskExecutor:
    """Facade that dispatches payloads to safe predefined executors."""

    def __init__(self) -> None:
        self._executors: dict[str, BaseExecutor] = {
            "CALCULATE": CalculateExecutor(),
            "DELAY": DelayExecutor(),
            "DATA_PROCESSING": DataProcessingExecutor(),
            "SEND_NOTIFICATION": SendNotificationExecutor(),
            "FAIL": FailExecutor(),
        }

    def register(self, task_type: str, executor: BaseExecutor) -> None:
        self._executors[task_type.upper()] = executor

    def execute(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        payload = payload or {}
        task_type = str(payload.get("type", "CALCULATE")).upper()
        executor = self._executors.get(task_type)
        if executor is None:
            raise TaskExecutionError(
                f"Unknown task type '{task_type}'. "
                f"Allowed: {', '.join(sorted(self._executors))}."
            )
        return executor.execute(payload)

    @property
    def supported_types(self) -> list[str]:
        return sorted(self._executors.keys())
