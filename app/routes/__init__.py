"""HTTP routes package."""

from flask import Flask


def register_blueprints(app: Flask) -> None:
    from app.routes.task_routes import task_bp
    from app.routes.worker_routes import worker_bp
    from app.routes.system_routes import system_bp
    from app.routes.dashboard_routes import dashboard_bp

    app.register_blueprint(task_bp, url_prefix="/api/tasks")
    app.register_blueprint(worker_bp, url_prefix="/api/workers")
    app.register_blueprint(system_bp, url_prefix="/api/system")
    app.register_blueprint(dashboard_bp)
