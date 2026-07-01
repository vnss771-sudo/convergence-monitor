"""Convergence Monitor service entry point.

Starts the pipeline, then runs:
  - HTTP status server on $PORT (foreground, main thread)
  - Pipeline scheduler in a background daemon thread

On startup the pipeline runs immediately so /status is populated before
the first scheduled refresh.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path

# Ensure the project root is on sys.path when invoked directly.
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _configure_logging() -> None:
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        stream=sys.stdout,
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main() -> int:
    _configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("Convergence Monitor starting up")

    from app.daemon import PipelineScheduler, StatusServer, REFRESH_INTERVAL_HOURS, PORT

    scheduler = PipelineScheduler()
    server = StatusServer(scheduler, port=PORT)

    # Run the pipeline immediately so /status is populated on first request.
    logger.info("Running initial pipeline pass...")
    scheduler.run_once()

    # Schedule future pipeline runs in a background thread.
    scheduler_thread = threading.Thread(
        target=scheduler.run_forever,
        kwargs={"interval_hours": REFRESH_INTERVAL_HOURS},
        daemon=True,
        name="pipeline-scheduler",
    )
    scheduler_thread.start()
    logger.info("Pipeline scheduler started (interval=%.1fh)", REFRESH_INTERVAL_HOURS)

    # HTTP server runs in the main thread (blocks until SIGTERM).
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down")
        server.shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
