"""Compatibility module — runtime lives in services.worker_service."""

from app.services.worker_service import WorkerRuntime

__all__ = ["WorkerRuntime"]
