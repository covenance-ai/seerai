"""Cloud-portable structured logging.

Emits JSON to stdout. Both GCP Cloud Logging and Yandex Cloud Logging
auto-ingest JSON lines from a container's stdout and parse standard fields
(`severity`, `message`, `time`) into structured log entries.

Used to be `google.cloud.logging.Client().setup_logging()` — that worked only
on GCP and added a heavy dep. Stdout-JSON is the same effective behaviour
without coupling to a cloud SDK.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    """Format records as one JSON object per line.

    Field choices match what Cloud Logging providers parse: `severity` for
    the level (GCP convention; YC also accepts `level`, so we emit both),
    `message` for the rendered text, `time` as RFC3339 UTC. Exception info
    is captured in `stack_trace` if present.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "severity": record.levelname,
            "level": record.levelname.lower(),
            "message": record.getMessage(),
            "time": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "logger": record.name,
        }
        if record.exc_info:
            payload["stack_trace"] = self.formatException(record.exc_info)
        # Pass through any extra=... keys from the call site.
        for k, v in record.__dict__.items():
            if k in payload or k.startswith("_"):
                continue
            if k in {"args", "asctime", "created", "exc_info", "exc_text",
                     "filename", "funcName", "levelname", "levelno",
                     "lineno", "module", "msecs", "msg", "name",
                     "pathname", "process", "processName", "relativeCreated",
                     "stack_info", "thread", "threadName", "taskName"}:
                continue
            try:
                json.dumps(v)
            except (TypeError, ValueError):
                v = repr(v)
            payload[k] = v
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: int | str | None = None) -> None:
    """Install the JSON formatter on the root logger.

    Idempotent — calling twice does not duplicate handlers. Honors
    ``LOG_LEVEL`` env var; falls back to INFO.
    """
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO")
    root = logging.getLogger()
    root.setLevel(level)
    # Replace any existing handlers so we don't double-emit (basicConfig may
    # have been called earlier during import).
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
