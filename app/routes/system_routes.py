"""System monitoring endpoints."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from app.services.task_service import TaskService

system_bp = Blueprint("system", __name__)
task_service = TaskService()


@system_bp.get("/stats")
def system_stats():
    """
    System statistics
    ---
    tags:
      - System
    responses:
      200:
        description: Aggregate counters
    """
    stats = task_service.get_stats()
    runtime = current_app.extensions.get("runtime")
    if runtime:
        stats["scheduler_state"] = runtime.scheduler.state.value
        stats["queue_size"] = runtime.task_queue.size()
    return jsonify(stats), 200


@system_bp.get("/health")
def health():
    """
    Health check
    ---
    tags:
      - System
    responses:
      200:
        description: OK
    """
    return jsonify({"status": "ok"}), 200
