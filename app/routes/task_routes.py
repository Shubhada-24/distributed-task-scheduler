"""Task REST endpoints."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.services.task_service import TaskService
from app.utils.logger import get_logger
from app.utils.validators import ValidationError

task_bp = Blueprint("tasks", __name__)
logger = get_logger("api")
task_service = TaskService()


@task_bp.post("")
def create_task():
    """
    Create a new task
    ---
    tags:
      - Tasks
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - task_name
          properties:
            task_name:
              type: string
            description:
              type: string
            priority:
              type: string
              enum: [LOW, MEDIUM, HIGH, CRITICAL]
            payload:
              type: object
            scheduled_at:
              type: string
              format: date-time
              nullable: true
            max_retries:
              type: integer
    responses:
      201:
        description: Task created
      400:
        description: Bad request
      422:
        description: Validation error
    """
    data = request.get_json(silent=True)
    task = task_service.create_task(data)
    # Notify in-memory queue remover is a no-op for creates; scheduler will pick up
    return jsonify(task.to_dict()), 201


@task_bp.get("")
def list_tasks():
    """
    List tasks with optional filters and pagination
    ---
    tags:
      - Tasks
    parameters:
      - in: query
        name: status
        type: string
      - in: query
        name: priority
        type: string
      - in: query
        name: page
        type: integer
        default: 1
      - in: query
        name: limit
        type: integer
        default: 20
    responses:
      200:
        description: Paginated task list
    """
    page = request.args.get("page", 1, type=int)
    limit = request.args.get("limit", 20, type=int)
    status = request.args.get("status")
    priority = request.args.get("priority")
    result = task_service.list_tasks(
        status=status, priority=priority, page=page, limit=limit
    )
    return jsonify(result), 200


@task_bp.get("/<int:task_id>")
def get_task(task_id: int):
    """
    Get a task by ID
    ---
    tags:
      - Tasks
    parameters:
      - in: path
        name: task_id
        type: integer
        required: true
    responses:
      200:
        description: Task details
      404:
        description: Not found
    """
    task = task_service.get_task(task_id)
    if task is None:
        raise ValidationError("Task not found", 404)
    return jsonify(task.to_dict()), 200


@task_bp.delete("/<int:task_id>")
def delete_task(task_id: int):
    """
    Delete a task
    ---
    tags:
      - Tasks
    parameters:
      - in: path
        name: task_id
        type: integer
        required: true
    responses:
      200:
        description: Deleted
      404:
        description: Not found
      409:
        description: Conflict
    """
    deleted = task_service.delete_task(task_id)
    if not deleted:
        raise ValidationError("Task not found", 404)
    runtime = current_app.extensions.get("runtime")
    if runtime:
        runtime.scheduler.sync_cancel(task_id)
    return jsonify({"message": "Task deleted", "id": task_id}), 200


@task_bp.post("/<int:task_id>/cancel")
def cancel_task(task_id: int):
    """
    Cancel a pending/scheduled/retrying task
    ---
    tags:
      - Tasks
    parameters:
      - in: path
        name: task_id
        type: integer
        required: true
    responses:
      200:
        description: Cancelled
      404:
        description: Not found
      409:
        description: Not cancellable
    """
    task = task_service.cancel_task(task_id)
    runtime = current_app.extensions.get("runtime")
    if runtime:
        runtime.scheduler.sync_cancel(task_id)
    return jsonify(task.to_dict()), 200


@task_bp.post("/<int:task_id>/retry")
def retry_task(task_id: int):
    """
    Manually retry a failed task
    ---
    tags:
      - Tasks
    parameters:
      - in: path
        name: task_id
        type: integer
        required: true
    responses:
      200:
        description: Queued for retry
      404:
        description: Not found
      409:
        description: Not retryable
    """
    task = task_service.retry_task(task_id)
    return jsonify(task.to_dict()), 200


@task_bp.get("/<int:task_id>/executions")
def task_executions(task_id: int):
    """
    List execution history for a task
    ---
    tags:
      - Tasks
    parameters:
      - in: path
        name: task_id
        type: integer
        required: true
    responses:
      200:
        description: Execution list
      404:
        description: Not found
    """
    executions = task_service.get_executions(task_id)
    return jsonify({"task_id": task_id, "executions": executions}), 200
