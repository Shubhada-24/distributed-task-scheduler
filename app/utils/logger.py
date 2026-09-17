"""Application logging setup."""

from __future__ import annotations

import logging
import logging.config
import os
from pathlib import Path


def setup_logging(log_level: str = "INFO") -> None:
    """Configure structured logging for the application."""
    config_path = Path(__file__).resolve().parents[2] / "config" / "logging.conf"
    if config_path.exists():
        logging.config.fileConfig(
            config_path,
            disable_existing_loggers=False,
            defaults={"log_level": log_level.upper()},
        )
    else:
        logging.basicConfig(
            level=getattr(logging, log_level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


def get_logger(name: str) -> logging.Logger:
    """Return a named logger (component appears in the [name] field)."""
    return logging.getLogger(name)
