"""Shared persistence and time helpers.

Centralizes the project's JSON artifact contract so that every writer produces
byte-identical, deterministic output and writes atomically (write to a temp file
in the same directory, then ``os.replace``), preventing partially-written or
corrupted artifacts if a process is interrupted mid-write.

The JSON contract is intentionally fixed: ``indent=2, sort_keys=True,
ensure_ascii=False`` with a trailing newline. Reproducibility tests (golden and
byte-stability) depend on this exact form, so do not change it casually.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator


def utc_now_iso() -> str:
    """Return the current UTC time as a stable ``...Z`` ISO-8601 string.

    Seconds resolution, no microseconds, ``Z`` suffix — the format every record
    timestamp in this project uses.
    """
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def dumps_canonical(obj: Any) -> str:
    """Serialize ``obj`` using the project's canonical JSON contract (no newline)."""
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False)


def write_json_atomic(path: Path | str, obj: Any) -> Path:
    """Atomically write ``obj`` as canonical JSON (with trailing newline) to ``path``.

    Creates parent directories as needed. Writes to a temporary file in the same
    directory and ``os.replace``s it into place so readers never observe a partial
    file.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = dumps_canonical(obj) + "\n"

    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        # Best-effort cleanup of the temp file on any failure.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return path


def read_json(path: Path | str) -> Any:
    """Read and parse a JSON file written by :func:`write_json_atomic`."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def iter_jsonl(path: Path | str) -> Iterator[dict[str, Any]]:
    """Yield parsed objects from a JSONL file, skipping blank lines.

    Malformed lines raise ``json.JSONDecodeError`` — callers that want to tolerate
    corruption should handle it explicitly rather than have it silently swallowed.
    """
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)
