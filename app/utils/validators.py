"""Input validation helpers for API payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models.task import TaskPriority


class ValidationError(Exception):
    """Raised when request data fails validation."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def require_fields(data: dict[str, Any], fields: list[str]) -> None:
    missing = [f for f in fields if f not in data or data[f] is None or data[f] == ""]
    if missing:
        raise ValidationError(f"Missing required field(s): {', '.join(missing)}", 400)


def parse_priority(value: Any) -> TaskPriority:
    if value is None:
        return TaskPriority.MEDIUM
    if isinstance(value, int):
        try:
            return TaskPriority(value)
        except ValueError as exc:
            raise ValidationError(
                f"Invalid priority value: {value}. Use LOW, MEDIUM, HIGH, or CRITICAL.",
                422,
            ) from exc
    if isinstance(value, str):
        try:
            return TaskPriority.from_name(value)
        except ValueError as exc:
            raise ValidationError(
                f"Invalid priority: {value}. Use LOW, MEDIUM, HIGH, or CRITICAL.",
                422,
            ) from exc
    raise ValidationError("Priority must be a string or integer.", 422)


def parse_scheduled_at(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
            return dt.replace(tzinfo=None) if dt.tzinfo else dt
        except ValueError as exc:
            raise ValidationError(
                "scheduled_at must be an ISO-8601 datetime string.", 422
            ) from exc
    raise ValidationError("scheduled_at must be a string or null.", 422)


def validate_payload(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValidationError("payload must be a JSON object.", 422)
    return payload


def validate_max_retries(value: Any, default: int = 3) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValidationError("max_retries must be an integer >= 0.", 422)
    if value < 0:
        raise ValidationError("max_retries must be >= 0.", 422)
    return value


def validate_task_create(data: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object.", 400)
    require_fields(data, ["task_name"])
    task_name = data["task_name"]
    if not isinstance(task_name, str) or not task_name.strip():
        raise ValidationError("task_name must be a non-empty string.", 422)
    if len(task_name) > 120:
        raise ValidationError("task_name must be at most 120 characters.", 422)

    description = data.get("description")
    if description is not None and not isinstance(description, str):
        raise ValidationError("description must be a string.", 422)

    return {
        "task_name": task_name.strip(),
        "description": description,
        "priority": parse_priority(data.get("priority")),
        "payload": validate_payload(data.get("payload")),
        "scheduled_at": parse_scheduled_at(data.get("scheduled_at")),
        "max_retries": validate_max_retries(data.get("max_retries")),
    }
