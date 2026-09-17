"""Worker REST endpoints."""

from __future__ import annotations

from flask import Blueprint, jsonify

from app.services.worker_service import WorkerService
from app.utils.validators import ValidationError

worker_bp = Blueprint("workers", __name__)
worker_service = WorkerService  # type used via methods below


@worker_bp.get("")
def list_workers():
    """
    List all workers
    ---
    tags:
      - Workers
    responses:
      200:
        description: Worker list
    """
    from app.extensions import db
    from app.models.worker import Worker
    from sqlalchemy import select

    workers = db.session.scalars(select(Worker).order_by(Worker.id)).all()
    return jsonify({"items": [w.to_dict() for w in workers]}), 200


@worker_bp.get("/<int:worker_id>")
def get_worker(worker_id: int):
    """
    Get worker by ID
    ---
    tags:
      - Workers
    parameters:
      - in: path
        name: worker_id
        type: integer
        required: true
    responses:
      200:
        description: Worker details
      404:
        description: Not found
    """
    from app.extensions import db
    from app.models.worker import Worker

    worker = db.session.get(Worker, worker_id)
    if worker is None:
        raise ValidationError("Worker not found", 404)
    return jsonify(worker.to_dict()), 200
