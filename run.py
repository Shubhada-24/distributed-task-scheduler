"""Application entry point."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

from app import create_app  # noqa: E402

app = create_app(os.getenv("FLASK_ENV", "development"))


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    # use_reloader=False so background threads are not duplicated
    app.run(host=host, port=port, debug=app.config.get("DEBUG", False), use_reloader=False)
