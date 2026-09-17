"""Application factory and runtime lifecycle management."""

from __future__ import annotations

import atexit
import os
from dataclasses import dataclass

from flasgger import Swagger
from flask import Flask, jsonify
from flask_cors import CORS

from app.config import config_by_name
from app.extensions import db, migrate
from app.routes import register_blueprints
from app.scheduler.priority_queue import PriorityTaskQueue
from app.services.scheduler_service import SchedulerService
from app.services.worker_service import WorkerService
from app.utils.logger import get_logger, setup_logging
from app.utils.validators import ValidationError

logger = get_logger("app")


@dataclass
class RuntimeComponents:
    task_queue: PriorityTaskQueue
    scheduler: SchedulerService
    worker_service: WorkerService


def create_app(config_name: str | None = None) -> Flask:
    """Create and configure the Flask application."""
    config_name = config_name or os.getenv("FLASK_ENV", "development")
    config_cls = config_by_name.get(config_name, config_by_name["default"])

    setup_logging(getattr(config_cls, "LOG_LEVEL", "INFO"))

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_cls)

    # Allow per-test SQLite paths without re-importing config module.
    if config_name == "testing":
        test_uri = os.getenv("TEST_DATABASE_URL")
        if test_uri:
            app.config["SQLALCHEMY_DATABASE_URI"] = test_uri
            app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
                "connect_args": {"check_same_thread": False},
            }

    db.init_app(app)
    migrate.init_app(app, db)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    Swagger(
        app,
        template={
            "swagger": "2.0",
            "info": {
                "title": "Distributed Task Scheduler API",
                "description": (
                    "REST API for creating, scheduling, monitoring, and retrying "
                    "background tasks with priority-based workers."
                ),
                "version": "1.0.0",
            },
            "basePath": "/",
            "schemes": ["http"],
        },
    )

    register_blueprints(app)
    register_error_handlers(app)

    # Import models so Flask-Migrate discovers them
    from app import models  # noqa: F401

    auto_start = app.config.get("AUTO_START_RUNTIME", True)
    skip_runtime = os.getenv("FLASK_SKIP_RUNTIME", "0") == "1"
    if app.config.get("TESTING"):
        # Provide queue/scheduler objects for tests that start them manually
        queue = PriorityTaskQueue()
        scheduler = SchedulerService(
            app, queue, poll_interval=app.config["SCHEDULER_POLL_INTERVAL"]
        )
        workers = WorkerService(
            app,
            queue,
            num_workers=app.config["NUM_WORKERS"],
            heartbeat_interval=app.config["WORKER_HEARTBEAT_INTERVAL"],
        )
        app.extensions["runtime"] = RuntimeComponents(queue, scheduler, workers)
    elif auto_start and not skip_runtime:
        _start_runtime(app)

    logger.info("Application startup complete (env=%s)", config_name)
    return app


def _start_runtime(app: Flask) -> None:
    queue = PriorityTaskQueue()
    scheduler = SchedulerService(
        app, queue, poll_interval=app.config["SCHEDULER_POLL_INTERVAL"]
    )
    workers = WorkerService(
        app,
        queue,
        num_workers=app.config["NUM_WORKERS"],
        heartbeat_interval=app.config["WORKER_HEARTBEAT_INTERVAL"],
    )
    runtime = RuntimeComponents(queue, scheduler, workers)
    app.extensions["runtime"] = runtime

    create_schema = os.getenv("SKIP_CREATE_ALL", "0") != "1"
    if create_schema:
        with app.app_context():
            db.create_all()

    scheduler.start()
    workers.start()

    def _shutdown() -> None:
        logger.info("Shutting down runtime components")
        scheduler.stop()
        workers.stop()

    atexit.register(_shutdown)


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ValidationError)
    def handle_validation(err: ValidationError):
        logger.warning("Validation error: %s", err.message)
        return jsonify({"error": err.message, "status": err.status_code}), err.status_code

    @app.errorhandler(400)
    def bad_request(err):
        return jsonify({"error": getattr(err, "description", "Bad request"), "status": 400}), 400

    @app.errorhandler(404)
    def not_found(err):
        return jsonify({"error": getattr(err, "description", "Not found"), "status": 404}), 404

    @app.errorhandler(409)
    def conflict(err):
        return jsonify({"error": getattr(err, "description", "Conflict"), "status": 409}), 409

    @app.errorhandler(422)
    def unprocessable(err):
        return jsonify(
            {"error": getattr(err, "description", "Unprocessable entity"), "status": 422}
        ), 422

    @app.errorhandler(500)
    def server_error(err):
        logger.exception("Internal server error")
        message = "Internal server error"
        if app.debug:
            message = str(err)
        return jsonify({"error": message, "status": 500}), 500
