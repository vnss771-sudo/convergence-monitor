"""Convergence Monitor daemon: HTTP server + pipeline scheduler.

Exposes:
  GET /health   — always 200 {"status": "ok", ...}
  GET /status   — latest convergence_latest_status.json content
  GET /readyz   — 200 when a valid status exists, 503 otherwise

The pipeline scheduler re-runs every REFRESH_INTERVAL_HOURS (default 6).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from app.outputs.convergence_v2_writer import write_convergence_v2_status
from app.pipeline import run_pipeline

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_HOURS = float(os.environ.get("REFRESH_INTERVAL_HOURS", "6"))
STATUS_PATH = Path(os.environ.get("CONVERGENCE_STATUS_JSON", "data/runs/convergence_latest_status.json"))
PORT = int(os.environ.get("PORT", "8080"))
VERSION = "1.0.0"


class PipelineScheduler:
    """Runs the convergence pipeline on a schedule and holds the latest result."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: dict[str, Any] | None = None
        self._last_run_at: float = 0.0
        self._run_count: int = 0
        self._error_count: int = 0

    def run_once(self) -> None:
        logger.info("Pipeline run starting (run #%d)", self._run_count + 1)
        try:
            status = run_pipeline(status_path=STATUS_PATH)
            write_convergence_v2_status(status, path=str(STATUS_PATH))
            with self._lock:
                self._latest = status
                self._last_run_at = time.time()
                self._run_count += 1
            logger.info(
                "Pipeline run complete: level=%s confidence=%d",
                status.get("convergence_level"),
                status.get("confidence", 0),
            )
        except Exception as exc:
            self._error_count += 1
            logger.error("Pipeline run failed: %s", exc, exc_info=True)

    def run_forever(self, interval_hours: float = REFRESH_INTERVAL_HOURS) -> None:
        interval_seconds = interval_hours * 3600
        while True:
            time.sleep(interval_seconds)
            self.run_once()

    @property
    def latest(self) -> dict[str, Any] | None:
        with self._lock:
            return self._latest

    def health_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "status": "ok",
                "version": VERSION,
                "run_count": self._run_count,
                "error_count": self._error_count,
                "last_run_age_seconds": round(time.time() - self._last_run_at, 1) if self._last_run_at else None,
                "has_status": self._latest is not None,
            }


class _Handler(BaseHTTPRequestHandler):
    scheduler: PipelineScheduler  # set by StatusServer

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/health":
            self._json(200, self.scheduler.health_dict())
        elif path in ("/status", "/convergence/status"):
            latest = self.scheduler.latest
            if latest is None:
                # Try reading from disk as fallback
                latest = _read_status_from_disk()
            if latest is None:
                self._json(503, {"error": "status not yet available"})
            else:
                self._json(200, latest)
        elif path == "/readyz":
            latest = self.scheduler.latest or _read_status_from_disk()
            if latest and latest.get("convergence_level") not in (None, ""):
                self._json(200, {"ready": True})
            else:
                self._json(503, {"ready": False, "reason": "no valid status"})
        else:
            self._json(404, {"error": "not found"})

    def _json(self, code: int, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args: object) -> None:  # suppress default access log
        logger.debug("HTTP %s", fmt % args)


class StatusServer:
    def __init__(self, scheduler: PipelineScheduler, port: int = PORT) -> None:
        self._port = port
        # Bind the scheduler into the handler class via a subclass so multiple
        # servers can coexist without sharing module-level state.
        handler = type("BoundHandler", (_Handler,), {"scheduler": scheduler})
        self._server = HTTPServer(("0.0.0.0", port), handler)

    def serve_forever(self) -> None:
        logger.info("HTTP server listening on port %d", self._port)
        self._server.serve_forever()

    def shutdown(self) -> None:
        self._server.shutdown()


def _read_status_from_disk() -> dict[str, Any] | None:
    try:
        if STATUS_PATH.exists():
            return json.loads(STATUS_PATH.read_text())
    except Exception:
        pass
    return None
